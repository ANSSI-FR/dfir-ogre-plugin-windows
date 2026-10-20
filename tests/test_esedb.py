import io
import os
from unittest import TestCase
from zipfile import ZipFile

import pyesedb

from . import DATA_FOLDER


class TestEsedb(TestCase):
    def test_windows_11_24h2_database(self):
        # WebCache uses the same ESE page format as this small BITS sample.
        sample = os.path.join(DATA_FOLDER, "esedb", "qmgr-win11-24h2.zip")
        with ZipFile(sample) as archive:
            data = io.BytesIO(archive.read("qmgr.db"))

        database = pyesedb.file()
        database.open_file_object(data)
        try:
            self.assertIsNotNone(database.get_table_by_name("Jobs"))
            self.assertIsNotNone(database.get_table_by_name("Files"))
        finally:
            database.close()
