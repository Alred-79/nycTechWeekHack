# Ring findings — Track 02 Fraud Watch

## A. Timestamp fingerprint
- txns with second == :00 : **326** / 5000 (6.5%)  — uniform would be ~1.7%
- txns at exactly HH:00:00 : **6**
- total $ in :00-second txns : **$165,142.58**
- distinct accounts in :00-second txns : **68**
  ['AC-0001', 'AC-0005', 'AC-0009', 'AC-0010', 'AC-0011', 'AC-0013', 'AC-0016', 'AC-0017', 'AC-0025', 'AC-0026', 'AC-0027', 'AC-0035', 'AC-0041', 'AC-0047', 'AC-0050', 'AC-0051', 'AC-0052', 'AC-0053', 'AC-0055', 'AC-0070', 'AC-0072', 'AC-0074', 'AC-0077', 'AC-0080', 'AC-0081', 'AC-0085', 'AC-0087', 'AC-0089', 'AC-0093', 'AC-0097', 'AC-0108', 'AC-0110', 'AC-0113', 'AC-0118', 'AC-0124', 'AC-0126', 'AC-0128', 'AC-0132', 'AC-0139', 'AC-0144', 'AC-0151', 'AC-0156', 'AC-0162', 'AC-0174', 'AC-0176', 'AC-0181', 'AC-0185', 'AC-0187', 'AC-0199', 'AC-0203', 'AC-0205', 'AC-0208', 'AC-0218', 'AC-0220', 'AC-0223', 'AC-0224', 'AC-0226', 'AC-0230', 'AC-0231', 'AC-0233', 'AC-0245', 'AC-0250', 'AC-0253', 'AC-0268', 'AC-0270', 'AC-0277', 'AC-0294', 'AC-0300']

## B. Counterparty concentration
High-volume (>$5k) accounts funneling into <=3 counterparties:
```
            txns     total  n_cp  zero_sec_txns  zero_sec_frac
account_id                                                    
AC-0005       83  53896.22     2             83            1.0
AC-0009       42  29120.71     1             42            1.0
AC-0001       42  26985.76     1             42            1.0
```
- count: **3**, combined total **$110,002.69**

## C. Suspect cohort & shared destinations
Accounts that are >50% :00-second txns (the injected ring):
```
            txns     total  n_cp  zero_sec_txns  zero_sec_frac
account_id                                                    
AC-0005       83  53896.22     2             83       1.000000
AC-0009       42  29120.71     1             42       1.000000
AC-0010       61  27467.37    20             42       0.688525
AC-0001       42  26985.76     1             42       1.000000
AC-0011       52  25919.11    12             41       0.788462
```
- ring size: **5**
- ring total volume: **$163,389.17**
- ring exposure counting ONLY :00-second txns: **$161,750.90**  (hint ~= $161,751)
- ring accounts: ['AC-0005', 'AC-0009', 'AC-0010', 'AC-0001', 'AC-0011']

Counterparties receiving the ring's :00-second money:
```
                   amount  txns  from_accts
counterparty_id                            
AC-0007          29120.71    42           1
AC-0006          27736.13    42           1
AC-0002          26985.76    42           1
AC-0011          26819.97    42           1
AC-0009          26160.09    41           1
AC-0003          24928.24    41           1
```

## D. Account-open clustering
Open dates of ring accounts:
```
account_id
AC-0010   2026-02-10
AC-0001   2026-02-13
AC-0011   2026-02-16
AC-0005   2026-02-18
AC-0009   2026-02-18
```
