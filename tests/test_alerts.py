"""Los avisos se repiten según el plazo de CADA clave (no según el de la última llamada)."""
import tempfile
import time
import unittest
from pathlib import Path

from fantasy_agent.storage import Store


class AlertTtl(unittest.TestCase):
    def test_a_short_ttl_call_does_not_wipe_longer_ones(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            self.assertTrue(st.alert_is_new("largo", ttl_hours=24))
            st.db.execute("UPDATE alerts_sent SET ts = ? WHERE key = 'largo'", (time.time() - 3 * 3600,))
            st.db.commit()
            self.assertTrue(st.alert_is_new("corto", ttl_hours=1))          # otra clave con plazo de 1 h
            self.assertFalse(st.alert_is_new("largo", ttl_hours=24))        # la de 24 h sigue silenciada a las 3 h

    def test_it_comes_back_after_its_own_ttl(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            self.assertTrue(st.alert_is_new("x", ttl_hours=2))
            self.assertFalse(st.alert_is_new("x", ttl_hours=2))
            st.db.execute("UPDATE alerts_sent SET ts = ? WHERE key = 'x'", (time.time() - 3 * 3600,))
            st.db.commit()
            self.assertTrue(st.alert_is_new("x", ttl_hours=2))


if __name__ == "__main__":
    unittest.main()
