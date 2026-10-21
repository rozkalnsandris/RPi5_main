#!/usr/bin/env python3
import importlib.util, json, tempfile, unittest, zipfile
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
    def test_source_contract(self):
        source=MODULE.read_text()
        self.assertNotIn("extractall(",source);self.assertNotIn('"0.0.0.0"',source);self.assertNotIn("rclone",source.lower())
        self.assertIn('HOST = "127.0.0.1"',source);self.assertIn("PUBLISH_LOCK",source)
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
        self.assertIn('class="dashboard-nav"',html)
        self.assertIn('href="https://ausmalwiese.de/stats.html"',html)
        self.assertIn('href="https://ausmalwiese.de/traffic.html"',html)
        self.assertIn("/assets/fonts/baloo2-latin-vf-26fb4610d4bc976d.woff2",html)
        self.assertIn("/assets/fonts/nunito-latin-vf-ba344451eab25b21.woff2",html)
        installer=(ROOT/"scripts/install-coloring-pages-admin-publish-v1.sh").read_text()
        self.assertIn("26fb4610d4bc976d2584ca15e66c11465dbc1f267a10dca668fcb3080dfe59c1",installer)
        self.assertIn("ba344451eab25b217a165363b1982048a5e5830a0daf36577973955a04cac793",installer)
        self.assertIn("/api/uploads",html);self.assertIn("/api/jobs",html)
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

if __name__=="__main__":unittest.main()
