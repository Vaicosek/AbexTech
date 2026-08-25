"""The parcel register answers from core, and answers "empty" when it is empty.

This exists because the register spent its whole life returning 503
`estates_db_unavailable` — it read a second database, `estates.db`, through an
`estates_db` module that is not in this repository and never was. On a page about
land, "the parcel register is unavailable" reads as an outage. It was not an
outage. The register had simply never been wired to the tables that hold the data,
`land_leases` and `land_rent_charges`, which are in core and always have been.

So the two things proved here are the two things that were wrong:

  1. An empty register returns ok with zero rows — not a 503. "Nobody has leased
     anything" and "the service is down" are opposite facts and the page has to be
     able to tell them apart.
  2. A parcel with a lease and an outstanding charge comes back with the charge
     attached, keyed by the same `land:parcel:<id>:rent:<period>` string the
     collector mints, so the figure on screen and the figure in the ledger key are
     produced by one function rather than two that agree today.
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import land_stubs  # noqa: E402

land_stubs.install()
land_stubs.install_core()

OWNER = "700000000000000011"
TENANT = "700000000000000012"


def test_empty_register_is_ok_not_unavailable():
    with tempfile.TemporaryDirectory() as tmp:
        with land_stubs.fresh_db(tmp):
            import estates_web as ew
            rows, period, due = ew._parcel_register()
            assert rows == [], rows
            assert due == []
            assert period, "a period label is always produced"


def test_lease_and_charge_appear_on_the_register():
    with tempfile.TemporaryDirectory() as tmp:
        with land_stubs.fresh_db(tmp) as db:
            import land_settle
            import estates_web as ew

            lease_id = db.create_land_lease("plot-17", TENANT, OWNER, 500,
                                            period_days=30,
                                            next_due_at="2026-09-01 00:00:00")
            lease = db.get_land_lease(lease_id)
            period = land_settle.rent_period(lease)
            key = land_settle.rent_key("plot-17", period)
            db.open_rent_charge(lease, period, key)

            rows, reg_period, due = ew._parcel_register()
            assert reg_period == period, (reg_period, period)
            assert len(rows) == 1, rows
            row = rows[0]
            assert row["slug"] == "plot-17"
            assert row["status"] == "leased"
            assert row["owner_id"] == OWNER
            assert row["tenant_id"] == TENANT
            assert row["rent"] == 500

            assert len(due) == 1, due
            assert due[0]["idem_key"] == key
            assert due[0]["parcel_id"] == "plot-17"
            # The register keys charges by the parcel SLUG, which is what
            # `h_parcels` looks up. A mismatch here is silently "nothing due" on a
            # parcel that is in arrears.
            assert str(due[0]["parcel_id"]) == row["slug"]


if __name__ == "__main__":
    test_empty_register_is_ok_not_unavailable()
    test_lease_and_charge_appear_on_the_register()
    print("parcel register: ok")
