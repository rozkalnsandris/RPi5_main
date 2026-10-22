#!/usr/bin/env python3
import importlib.util, json, os, stat, tempfile, unittest, zipfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/"ops/bin/coloring-pages-admin-publish"
loader=SourceFileLoader("admin_publish",str(MODULE))
spec=importlib.util.spec_from_loader(loader.name,loader)
admin=importlib.util.module_from_spec(spec);loader.exec_module(admin)

def png_stub(w=1024,h=1536):
    import struct
    return admin.PNG_SIG + b"\x00\x00\x00\rIHDR" + struct.pack(">II",w,h) + b"\x08\x02\x00\x00\x00" + b"x"*64

class Tests(unittest.TestCase):
    def make_zip(self,entries):
        p=Path(self.tmp.name)/"x.zip"
        with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:
            for n,b in entries:z.writestr(n,b)
        return p
    def setUp(self):self.tmp=tempfile.TemporaryDirectory()
    def tearDown(self):self.tmp.cleanup()
    def test_good_zip(self):
        z=self.make_zip([("1-reh.png",png_stub()),("2-fuchs.png",png_stub())]);out=Path(self.tmp.name)/"u";out.mkdir()
        result=admin.stage_zip(z,out)
        self.assertEqual(result["count"],2);self.assertEqual(result["files"][0]["title"],"Reh")
    def test_nested_rejected(self):
        z=self.make_zip([("../evil.png",png_stub())]);out=Path(self.tmp.name)/"u";out.mkdir()
        with self.assertRaises(admin.Stop):admin.stage_zip(z,out)
    def test_non_png_rejected(self):
        z=self.make_zip([("x.txt",b"x")]);out=Path(self.tmp.name)/"u";out.mkdir()
        with self.assertRaises(admin.Stop):admin.stage_zip(z,out)
    def test_bad_dimensions_rejected(self):
        z=self.make_zip([("x.png",png_stub(100,100))]);out=Path(self.tmp.name)/"u";out.mkdir()
        with self.assertRaises(admin.Stop):admin.stage_zip(z,out)
    def test_titles(self):
        self.assertEqual(admin.title_from_name("01-mein_fuchs.png"),"Mein Fuchs")
        self.assertEqual(admin.validate_title("  Mein   Bild  "),"Mein Bild")
    def test_ids_avoid_collision(self):
        values=iter([1234567,7654321])
        old_random=admin.secrets.randbelow
        old_catalog=admin.catalog_ids
        admin.secrets.randbelow=lambda n:next(values)
        admin.catalog_ids=lambda:{"1234567"}
        try:self.assertEqual(admin.allocate_ids(1),["7654321"])
        finally:
            admin.secrets.randbelow=old_random
            admin.catalog_ids=old_catalog

    def test_catalog_atomic_write_and_stale_precondition(self):
        old_catalog=admin.CATALOG
        catalog=Path(self.tmp.name)/"catalog.json"
        initial=[{
            "id":"1234567","title":"Alt","character":"","category":"tiere",
            "age":"3-6","difficulty":"easy","language":"de",
            "thumb":"/media/1234567/thumb.webp","preview":"/media/1234567/preview.webp",
            "print":"/media/1234567/print.png","keep":"yes",
        }]
        catalog.write_text(json.dumps(initial,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        admin.CATALOG=catalog
        try:
            entries,sha=admin.load_catalog()
            entries[0]["title"]="Neu"
            new_sha=admin.write_catalog(entries,sha)
            saved,check_sha=admin.load_catalog()
            self.assertEqual(check_sha,new_sha)
            self.assertEqual(saved[0]["title"],"Neu")
            self.assertEqual(saved[0]["keep"],"yes")
            before=catalog.read_bytes()
            with self.assertRaises(admin.Stop):
                admin.write_catalog(saved,"0"*64)
            self.assertEqual(catalog.read_bytes(),before)
        finally:
            admin.CATALOG=old_catalog

    def test_catalog_validators(self):
        self.assertEqual(admin.validate_catalog_id("cp-000001"),"cp-000001")
        self.assertEqual(admin.validate_catalog_id("1234567"),"1234567")
        self.assertEqual(admin.validate_age("3-6"),"3-6")
        self.assertEqual(admin.validate_difficulty("detailed"),"detailed")
        for bad in ("../x","ABC",""):
            with self.assertRaises(admin.Stop):admin.validate_catalog_id(bad)
        with self.assertRaises(admin.Stop):admin.validate_age("9-12")
        with self.assertRaises(admin.Stop):admin.validate_difficulty("hard")

    def test_reconcile_interrupted_job_preserves_results(self):
        old_jobs,old_audit=admin.JOBS,admin.audit
        jobs=Path(self.tmp.name)/"jobs";jobs.mkdir()
        admin.JOBS=jobs;events=[]
        admin.audit=lambda event,**fields:events.append((event,fields))
        payload={
            "job_id":"a"*32,"upload_id":"b"*32,"status":"running",
            "steps":[{"label":"Import","status":"running","started_at":1}],
            "results":[{"id":"1234567","title":"P","status":"imported"}],
        }
        jobdir=jobs/("a"*32);jobdir.mkdir();admin.write_json(jobdir/"job.json",payload)
        try:
            self.assertEqual(admin.reconcile_interrupted_jobs(),1)
            saved=admin.read_json(jobdir/"job.json")
            self.assertEqual(saved["status"],"failed")
            self.assertTrue(saved["interrupted"])
            self.assertEqual(saved["error"],"publication interrupted by service restart")
            self.assertEqual(saved["results"],payload["results"])
            self.assertEqual(saved["steps"][0]["status"],"failed")
            self.assertEqual(events[0][0],"stale_job_reconciled")
            self.assertEqual(events[0][1]["partial_result_count"],1)
        finally:
            admin.JOBS,admin.audit=old_jobs,old_audit

    def test_active_job_returns_single_persisted_job(self):
        old_jobs=admin.JOBS
        jobs=Path(self.tmp.name)/"active";jobs.mkdir()
        admin.JOBS=jobs
        payload={"job_id":"c"*32,"status":"queued"}
        jobdir=jobs/("c"*32);jobdir.mkdir();admin.write_json(jobdir/"job.json",payload)
        try:self.assertEqual(admin.active_job()["job_id"],"c"*32)
        finally:admin.JOBS=old_jobs

    def test_log_prune_is_age_bounded_and_allowlisted(self):
        old_logs,old_file=admin.LOGS,admin.LOG_FILE
        logs=Path(self.tmp.name)/"logs";logs.mkdir()
        admin.LOGS=logs;admin.LOG_FILE=logs/"admin-publish.log"
        old=logs/"admin-publish.log.2026-10-01";old.write_text("x")
        unrelated=logs/"keep-me.txt";unrelated.write_text("x")
        now=10_000_000
        os.utime(old,(now-admin.LOG_RETENTION_SECONDS-1,now-admin.LOG_RETENTION_SECONDS-1))
        os.utime(unrelated,(1,1))
        try:
            self.assertEqual(admin.prune_logs(now=now),1)
            self.assertFalse(old.exists())
            self.assertTrue(unrelated.exists())
        finally:
            admin.LOGS,admin.LOG_FILE=old_logs,old_file

    def test_logging_initialization_is_private_and_daily(self):
        old_logs,old_file,old_owner=admin.LOGS,admin.LOG_FILE,admin.owner_ids
        logs=Path(self.tmp.name)/"private-logs";logs.mkdir()
        admin.LOGS=logs;admin.LOG_FILE=logs/"admin-publish.log"
        admin.owner_ids=lambda:(os.getuid(),os.getgid())
        try:
            admin.init_logging()
            self.assertEqual(stat.S_IMODE(admin.LOG_FILE.stat().st_mode),0o600)
            self.assertEqual(len(admin.LOGGER.handlers),1)
            handler=admin.LOGGER.handlers[0]
            self.assertIsInstance(handler,admin.StrictTimedRotatingFileHandler)
            self.assertEqual(handler.backupCount,7)
            self.assertTrue(handler.utc)
            self.assertTrue({"headers","cookies","token","credentials","environment","stdout","stderr"}.isdisjoint(admin.LOG_ALLOWED_FIELDS))
        finally:
            for handler in list(admin.LOGGER.handlers):
                handler.close();admin.LOGGER.removeHandler(handler)
            admin.LOGS,admin.LOG_FILE,admin.owner_ids=old_logs,old_file,old_owner
    def test_source_contract(self):
        source=MODULE.read_text()
        self.assertNotIn("extractall(",source);self.assertNotIn('"0.0.0.0"',source);self.assertNotIn("rclone",source.lower())
        self.assertIn('HOST = "127.0.0.1"',source);self.assertIn("PUBLISH_LOCK",source)
        self.assertIn("ghcr.io/rozkalnsandris/coloring-pages@sha256:5e63d5c37807cd25ef3ff384ea6e0681fa5b6995b0d8eb2a5846e038327e4cb4",source)
        self.assertIn("VALIDATE_PRINT=PASS",source);self.assertIn("detail.html?id=",source)
        prepare=source.index('run_tool(PRINT_MASTER, ["prepare"')
        validate=source.index('run_tool(PRINT_MASTER, ["validate"')
        allocate=source.index("ids = allocate_ids")
        importer=source.index("output = run_tool(IMPORTER")
        self.assertLess(prepare,validate)
        self.assertLess(validate,allocate)
        self.assertLess(allocate,importer)
        self.assertIn('/assets/fonts/baloo2-latin-vf-26fb4610d4bc976d.woff2',source)
        self.assertIn('/assets/fonts/nunito-latin-vf-ba344451eab25b21.woff2',source)
        self.assertIn('path == "/api/catalog"',source)
        self.assertIn('path == "/api/catalog/edit"',source)
        self.assertIn('path == "/api/catalog/unpublish"',source)
        self.assertIn('"X-Ausmalwiese-CSRF"',source)
        self.assertIn('self.headers.get("If-Match")',source)
        self.assertIn('self.send_error_json(412',source)
        self.assertIn('os.replace(temp, CATALOG)',source)
        self.assertIn('with acquire_catalog_lock():',source)
        self.assertNotIn('shutil.rmtree(MEDIA',source)
        self.assertNotIn('shutil.rmtree(ORIGINALS',source)

class StaticTests(unittest.TestCase):
    def test_assets_and_contract(self):
        html=(ROOT/"ops/admin/coloring-pages/index.html").read_text()
        self.assertIn("Publicēt krāsojamās lapas",html);self.assertIn("Izvēlēties kategoriju",html)
        self.assertIn('<html lang="lv">',html);self.assertIn("--blue:#1474d4",html)
        self.assertIn('class="site-header"',html)
        self.assertIn('class="admin-hero"',html)
        self.assertIn('class="container workflow-grid"',html)
        self.assertIn("--container:1340px",html)
        self.assertNotIn("<aside",html)
        self.assertIn('font-family:"Baloo 2"',html);self.assertIn('font-family:"Nunito"',html)
        self.assertIn(".admin-hero h1{margin:5px 0 2px;font-family:var(--font-body)",html)
        self.assertIn(".panel-title h2{margin:0;font-family:var(--font-body)",html)
        self.assertIn(".process h3{margin:0 0 8px;font-family:var(--font-body)",html)
        self.assertIn(".success h3{margin:0;color:#1a753b;font-family:var(--font-body)",html)
        self.assertIn(".brand{display:inline-flex;align-items:center;gap:10px;justify-self:start;color:var(--text);text-decoration:none;font-family:var(--font-display)",html)
        self.assertIn('class="dashboard-nav"',html)
        self.assertIn(".dashboard-nav{display:flex;align-items:stretch;justify-self:center;height:70px;gap:36px}",html)
        self.assertIn(".dashboard-nav a{position:relative;display:grid;place-items:center;color:#1d2f4d;text-decoration:none;font-size:15px;font-weight:700}",html)
        self.assertIn(".skip-link:focus-visible{transform:translateY(0)}",html)
        self.assertNotIn(".skip-link:focus{transform:translateY(0)}",html)
        self.assertIn('href="https://ausmalwiese.de/stats.html"',html)
        self.assertIn('href="https://ausmalwiese.de/traffic.html"',html)
        self.assertIn("/assets/fonts/baloo2-latin-vf-26fb4610d4bc976d.woff2",html)
        self.assertIn("/assets/fonts/nunito-latin-vf-ba344451eab25b21.woff2",html)
        installer=(ROOT/"scripts/install-coloring-pages-admin-publish-v1.sh").read_text()
        self.assertIn("26fb4610d4bc976d2584ca15e66c11465dbc1f267a10dca668fcb3080dfe59c1",installer)
        self.assertIn("ba344451eab25b217a165363b1982048a5e5830a0daf36577973955a04cac793",installer)
        self.assertIn('MODE="${3:-full}"',installer)
        self.assertIn("OWNER-AUTHORIZED-AUSMALWIESE-ADMIN-UI-UPDATE",installer)
        self.assertIn("ACTIVE_PUBLICATION_REFUSES_ADMIN_UPDATE",installer)
        self.assertIn("ADMIN_ACTIVE_JOB_CHECK_FAILED",installer)
        self.assertIn("http://127.0.0.1:8765/api/jobs/active",installer)
        self.assertIn('[[ "$ACTIVE_STATE" == "idle" ]]',installer)
        self.assertIn('flock -n 9',installer)
        guard=installer.index("http://127.0.0.1:8765/api/jobs/active")
        binary_install=installer.index('install -o root -g root -m 0755 "$REPO/ops/bin/coloring-pages-admin-publish"')
        self.assertLess(guard,binary_install)
        ui_mode=installer.index('if [[ "$MODE" == "ui-only" ]]; then')
        ui_pass=installer.index('AUSMALWIESE_ADMIN_UI_UPDATE=PASS')
        daemon_reload=installer.index("systemctl daemon-reload")
        restart=installer.index('systemctl restart "$SERVICE"')
        self.assertLess(ui_mode,ui_pass)
        self.assertLess(ui_pass,daemon_reload)
        self.assertLess(ui_pass,restart)
        self.assertIn("READINESS_ATTEMPTS=10",installer)
        self.assertIn("READINESS_CURL_SECONDS=0.25",installer)
        self.assertIn("READINESS_INTERVAL_SECONDS=0.25",installer)
        self.assertIn("ADMIN_SERVICE_HTTP_NOT_READY",installer)
        self.assertEqual(installer.count('systemctl restart "$SERVICE"'),1)
        lifecycle=installer.index('systemctl restart "$SERVICE"')
        post_is_active=installer.index('systemctl is-active --quiet "$SERVICE"',lifecycle)
        readiness_loop=installer.index('for ((attempt=1; attempt<=READINESS_ATTEMPTS; attempt++)); do',post_is_active)
        font_verify=installer.index('http://127.0.0.1:8765/assets/fonts/$BALOO_NAME',readiness_loop)
        self.assertLess(lifecycle,post_is_active)
        self.assertLess(post_is_active,readiness_loop)
        self.assertLess(readiness_loop,font_verify)
        self.assertIn('sleep "$READINESS_INTERVAL_SECONDS"',installer)
        self.assertIn('--connect-timeout "$READINESS_CURL_SECONDS"',installer)
        self.assertIn('--max-time "$READINESS_CURL_SECONDS"',installer)
        self.assertIn("/api/uploads",html);self.assertIn("/api/jobs",html)
        self.assertIn("sessionStorage.setItem",html)
        self.assertIn('"/api/jobs/active"',html)
        self.assertIn("restoreActiveJob()",html)
        self.assertIn("scheduleRefresh(Math.min(10000",html)
        self.assertNotIn("clearInterval(poll)",html)
        self.assertIn("Daļēji pabeigts — jau apstrādātās lapas",html)
        self.assertIn('id="catalog-manager"',html)
        self.assertIn('id="catalogSearch"',html)
        self.assertIn('id="editDialog"',html)
        self.assertIn('"/api/catalog/edit"',html)
        self.assertIn('"/api/catalog/unpublish"',html)
        self.assertIn('"X-Ausmalwiese-CSRF"',html)
        self.assertIn('"If-Match":catalogEtag',html)
        self.assertIn('media/original faili paliks',html)
        self.assertIn("state/admin-publish/logs",installer)
        contract=json.loads((ROOT/"ops/contracts/coloring-pages-admin-publish-v1.json").read_text())
        self.assertEqual(contract["listener"],{"host":"127.0.0.1","port":8765})
        self.assertEqual(contract["publication"]["category_selection"],"explicit-owner-ui-selection")
        self.assertFalse(contract["publication"]["automatic_retry"])
        self.assertEqual(contract["publication"]["shared_lock"],"/srv/coloring-pages-content/state/drive-ingest/.lock")
        self.assertEqual(contract["upload"]["archive_role"],"draft-png-handoff-only")
        self.assertEqual(contract["upload"]["allowed_members"],"top-level-png-only-no-manifest-or-metadata-files")
        gate=contract["publication"]["print_quality_gate"]
        self.assertEqual(gate["execution_order"],["prepare-all","validate-all","allocate-ids","import"])
        self.assertTrue(gate["fail_before_id_allocation_on_any_prepare_or_validate_failure"])
        master=gate["prepared_master"]
        self.assertEqual(master["portrait_px"],[2480,3508])
        self.assertEqual(master["landscape_px"],[3508,2480])
        self.assertEqual(master["mode"],"RGB-no-alpha")
        self.assertEqual(master["dpi"],"approximately-300x300")
        self.assertEqual(master["outer_border"],"#FFFFFF")
        self.assertEqual(master["safe_margin_mm"],15)
        self.assertEqual(master["safe_margin_px_at_300_dpi"],177)
        self.assertEqual(master["safe_margin_color"],"#FFFFFF")
        self.assertEqual(master["fit"],"aspect-ratio-preserving-centered")
        self.assertEqual(contract["publication"]["zip_member_semantics"],"each-png-is-one-independent-single-page-activity")
        self.assertEqual(contract["runtime"]["source_sha"],"798b263671c81b4e034b163b263dce7dc18306eb")
        self.assertEqual(contract["runtime"]["image_ref"],"ghcr.io/rozkalnsandris/coloring-pages@sha256:5e63d5c37807cd25ef3ff384ea6e0681fa5b6995b0d8eb2a5846e038327e4cb4")
        manager=contract["catalog_management"]
        self.assertEqual(manager["issue"],1172)
        self.assertEqual(manager["validator"],"strong-sha256-etag")
        self.assertEqual(manager["write_precondition"],"If-Match-required")
        self.assertEqual(manager["editable_fields"],["title","category","age","difficulty"])
        self.assertFalse(manager["physical_delete"])
        self.assertFalse(manager["unpublish"]["media_deleted"])
        self.assertFalse(manager["unpublish"]["originals_deleted"])
        csrf=contract["trust"]["csrf"]
        self.assertEqual(csrf["header"],"X-Ausmalwiese-CSRF")
        self.assertEqual(csrf["fetch_metadata"],"reject-cross-site")
        maintenance=contract["maintenance"]
        self.assertIn("GET /api/jobs/active",maintenance["full_install_guard"])
        self.assertEqual(maintenance["active_or_unknown"],"fail-closed-no-install-no-restart")
        self.assertIn("no daemon-reload or service restart",maintenance["ui_only_mode"])
        readiness=maintenance["post_restart_readiness"]
        self.assertEqual(readiness["endpoint"],"http://127.0.0.1:8765/")
        self.assertEqual(readiness["attempts"],10)
        self.assertEqual(readiness["per_attempt_timeout_seconds"],0.25)
        self.assertEqual(readiness["interval_seconds"],0.25)
        self.assertLessEqual(readiness["max_window_seconds"],5)
        self.assertEqual(readiness["failure"],"terminal-no-second-restart-or-installer-retry")
        self.assertFalse(maintenance["automatic_retry"])
        self.assertFalse(maintenance["automatic_rollback"])
        self.assertFalse(maintenance["automatic_cleanup"])
        recovery=contract["recovery"]
        self.assertEqual(recovery["reload"],"restore-existing-job-and-resume-polling")
        self.assertEqual(recovery["transient_polling"],"bounded-exponential-backoff-max-10s-no-permanent-stop")
        self.assertEqual(recovery["post_restart"],"queued-or-running-persisted-jobs-become-failed-interrupted")
        self.assertTrue(recovery["preserve_partial_results"])
        self.assertFalse(recovery["automatic_retry"])
        self.assertFalse(recovery["automatic_requeue"])
        diagnostics=contract["diagnostics"]
        self.assertEqual(diagnostics["log_path"],"/srv/coloring-pages-content/state/admin-publish/logs/admin-publish.log")
        self.assertEqual(diagnostics["directory_mode"],"0700")
        self.assertEqual(diagnostics["file_mode"],"0600")
        self.assertEqual(diagnostics["rotation"]["handler"],"logging.handlers.TimedRotatingFileHandler")
        self.assertEqual(diagnostics["rotation"]["when"],"midnight")
        self.assertEqual(diagnostics["rotation"]["explicit_age_prune_days"],7)
        self.assertFalse(diagnostics["global_journald_retention_change"])
        forbidden=" ".join(diagnostics["forbidden"]).lower()
        for word in ("headers","cookies","tokens","credentials","environment","stdout","stderr","traceback"):
            self.assertIn(word,forbidden)

if __name__=="__main__":unittest.main()
