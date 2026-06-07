
## Shape & schema

- Rows: **5,000**  |  Columns: **9**
- Date range: **2026-03-03 02:00:00** → **2026-06-01 20:36:23** (90 days)
- Unique accounts: **294**  |  counterparties: **205**  |  devices: **292**

Column dtypes / null counts:
```
txn_id               str              nulls=0
account_id           str              nulls=0
counterparty_id      str              nulls=0
amount               float64          nulls=0
timestamp            datetime64[us]   nulls=0
merchant_category    str              nulls=0
device_id            str              nulls=0
ip_region            str              nulls=0
account_open_date    datetime64[us]   nulls=0
```

## Amount distribution (threshold-evasion check)

- min $1.36  median $31.05  mean $92.40  max $14,941.26
- total volume: **$462,007.48**
- txns in [900, 1,000) (just-under $1,000): **0**
- txns in [2,700, 3,000) (just-under $3,000): **0**
- txns in [4,500, 5,000) (just-under $5,000): **0**
- txns in [9,000, 10,000) (just-under $10,000): **1**
- txns >= $10,000 (CTR / structuring line): **6**

## Categorical breakdowns

Merchant categories:
```
merchant_category
services       940
retail         711
grocery        709
fuel           689
electronics    660
dining         654
travel         637
```
IP regions:
```
ip_region
CT    949
NJ    866
PA    855
NY    794
CA    776
FL    739
JP     13
FR      5
UK      3
```

## Per-account activity

- txns/account: min 6 median 16 max 83
- total$/account: median $703 max $53,896

Top 15 accounts by total volume:
```
            txns     total    mean_amt  n_devices  n_regions  n_counterparties               first                last
account_id                                                                                                            
AC-0005       83  53896.22  649.352048          1          1                 2 2026-03-04 02:32:00 2026-05-30 03:58:00
AC-0009       42  29120.71  693.350238          1          1                 1 2026-03-05 02:33:00 2026-05-28 03:57:00
AC-0010       61  27467.37  450.284754          1          1                20 2026-03-07 21:24:57 2026-05-29 03:39:00
AC-0001       42  26985.76  642.518095          1          1                 1 2026-03-03 02:00:00 2026-05-26 03:54:00
AC-0011       52  25919.11  498.444423          1          1                12 2026-03-04 11:35:48 2026-05-31 03:54:00
AC-0016       20  15977.29  798.864500          1          1                20 2026-03-07 10:54:29 2026-06-01 00:05:14
AC-0017       18  13316.71  739.817222          1          1                17 2026-03-04 23:43:17 2026-05-29 03:51:56
AC-0015       16  13261.30  828.831250          1          1                16 2026-03-08 21:52:31 2026-05-17 19:40:49
AC-0013       23  12829.25  557.793478          1          1                22 2026-03-06 03:34:53 2026-05-29 08:58:37
AC-0018       15  11640.12  776.008000          1          1                15 2026-03-14 11:05:35 2026-05-30 00:03:52
AC-0019       18  10728.03  596.001667          1          1                18 2026-03-04 21:32:39 2026-05-31 21:42:12
AC-0014       16   9839.06  614.941250          1          1                16 2026-03-15 19:26:11 2026-05-29 11:26:56
AC-0020       15   9048.86  603.257333          1          1                15 2026-03-08 16:06:49 2026-05-31 12:44:12
AC-0162       25   2128.25   85.130000          1          1                23 2026-03-17 22:19:16 2026-05-31 15:07:43
AC-0174       17   1749.15  102.891176          1          1                16 2026-03-06 13:14:33 2026-05-31 20:56:59
```

## Shared-infrastructure signals (ring hunting)

- devices used by >1 account: **2** (out of 292)
Top shared devices (device_id -> #distinct accounts):
```
device_id
DV-52001    2
DV-31829    2
```
- accounts touching the top-8 shared devices: **4**
  ['AC-0045', 'AC-0127', 'AC-0131', 'AC-0192']

Top counterparties by #distinct accounts paying them:
```
counterparty_id
MR-0123    38
MR-0063    38
MR-0084    36
MR-0017    34
MR-0064    33
MR-0109    33
MR-0156    32
MR-0007    32
MR-0039    32
MR-0041    31
MR-0048    31
MR-0011    31
MR-0037    30
MR-0043    30
MR-0118    30
```

## Candidate ring assembly

Accounts ranked by $ flowing through shared devices:
```
            shared_dev_txns  shared_dev_total  devices
account_id                                            
AC-0045                  14            989.98        1
AC-0131                  16            697.40        1
AC-0127                  23            697.31        1
AC-0192                  15            651.02        1
```
- Top-12 candidate exposure (via shared devices): **$3,035.71**  (target hint ~= $161,751)

## Temporal pattern

- See `out/daily_volume.png` for daily $ volume.
Txns by hour of day:
```
hour
0     204
1     197
2     317
3     319
4     206
5     197
6     194
7     184
8     203
9     206
10    211
11    197
12    186
13    179
14    210
15    188
16    190
17    211
18    188
19    193
20    210
21    214
22    198
23    198
```