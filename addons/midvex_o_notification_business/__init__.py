# Intentionally empty: this module is data only.
#
# `tests` is deliberately not imported here. Odoo's test loader imports the
# tests subpackage itself when running in test mode, and importing it from
# __init__ pulls the test framework into every normal server start — which
# Odoo logs as an error ("avoid importing from business modules and when not
# running in test mode").
