"""Minimal isolated package initializer for the Weather privileged stage helper.

This file is installed as deploy_executor/__init__.py inside the dedicated Weather
helper support root. It intentionally imports nothing so the root-owned helper
cannot inherit unrelated deploy-executor transport, state, credential, or
controller surfaces merely by importing its package.
"""
