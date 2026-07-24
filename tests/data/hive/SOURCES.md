# Registry hive fixture sources

## `NTUSER_RECENT_APPS.dat`

- Source:
  <https://raw.githubusercontent.com/mkorman90/regipy/f78c55ae67ad7672660a255569c20650de5564de/regipy_tests/data/transactions_NTUSER.DAT.xz>
- Upstream project: <https://github.com/mkorman90/regipy>
- Upstream commit: `f78c55ae67ad7672660a255569c20650de5564de`
- Upstream license: MIT; the complete copyright and permission notice is
  redistributed in [`licenses/regipy-MIT.txt`](licenses/regipy-MIT.txt).
- Stored form: XZ source decompressed once; registry hive bytes are otherwise
  unmodified.
- Size: 1,048,576 bytes
- SHA-256:
  `e47f18fb696e4f18ff7432348561e4393f20336b80d0dd88e9c134e5575ecae1`
- Relevant artifact:
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Search\RecentApps`

## `NTUSER_WORD_WHEEL_QUERY.dat`

- Source:
  <https://raw.githubusercontent.com/log2timeline/plaso/4ea03ef9a48dad5284c371ac9b537a184b3eea9c/test_data/NTUSER-WIN7.DAT>
- Upstream project: <https://github.com/log2timeline/plaso>
- Upstream commit: `4ea03ef9a48dad5284c371ac9b537a184b3eea9c`
- Upstream license: Apache License 2.0; the complete license is redistributed
  in
  [`licenses/plaso-Apache-2.0.txt`](licenses/plaso-Apache-2.0.txt).
- Upstream `4ea03ef9a48dad5284c371ac9b537a184b3eea9c` contains no `NOTICE` file.
- Stored form: raw upstream registry hive, unmodified.
- Size: 1,310,720 bytes
- SHA-256:
  `672abb15ae62fa8c002c5ee0a730cf83cd5f40706d5ffdec8f1179cf47a0bd03`
- Relevant artifact:
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\WordWheelQuery`
