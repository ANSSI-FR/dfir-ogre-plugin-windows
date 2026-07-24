# Registry hive fixture sources

## `NTUSER_RECENT_APPS.dat`

- Source:
  <https://github.com/mkorman90/regipy/raw/master/regipy_tests/data/transactions_NTUSER.DAT.xz>
- Upstream project: <https://github.com/mkorman90/regipy>
- Upstream license: MIT,
  <https://github.com/mkorman90/regipy/blob/master/LICENSE>
- Stored form: XZ source decompressed once; registry hive bytes are otherwise
  unmodified.
- Size: 1,048,576 bytes
- SHA-256:
  `e47f18fb696e4f18ff7432348561e4393f20336b80d0dd88e9c134e5575ecae1`
- Relevant artifact:
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Search\RecentApps`

## `NTUSER_WORD_WHEEL_QUERY.dat`

- Source:
  <https://github.com/log2timeline/plaso/raw/main/test_data/NTUSER-WIN7.DAT>
- Upstream project: <https://github.com/log2timeline/plaso>
- Upstream license: Apache License 2.0,
  <https://github.com/log2timeline/plaso/blob/main/LICENSE>
- Stored form: raw upstream registry hive, unmodified.
- Size: 1,310,720 bytes
- SHA-256:
  `672abb15ae62fa8c002c5ee0a730cf83cd5f40706d5ffdec8f1179cf47a0bd03`
- Relevant artifact:
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\WordWheelQuery`
