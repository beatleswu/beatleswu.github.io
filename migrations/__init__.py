"""Explicit, reviewable schema migrations.

Modules in this package never execute on import. Database mutations require an
operator or a test to call the selected migration function explicitly.
"""
