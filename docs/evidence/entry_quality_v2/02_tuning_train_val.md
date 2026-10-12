# Parametre seçimi (TRAIN tara → VALIDATION seç)

Kısıt: korunan sinyal payı ≥ 70% (train ve val). Hedef J' = −(bloklanan payı)×(bloklananların z'si − tüm sinyal z'si), grup (seri,tf) eşit ağırlık; z sürüklenme-ayarlı.

## TRAIN'de en iyi 5
| q_wait | reversal_wait | range_extreme | loc_floor | j_train | keep_train | j_val | keep_val | groups_pos_val | groups_val |
|---|---|---|---|---|---|---|---|---|---|
| 0.300 | 0.600 | 0.300 | 0.200 | 0.002 | 0.839 | -0.000 | 0.837 | 16.0 | 31.0 |
| 0.300 | 0.600 | 0.150 | 0.200 | 0.002 | 0.850 | -0.000 | 0.851 | 17.0 | 31.0 |
| 0.300 | 0.600 | 0.200 | 0.200 | 0.002 | 0.846 | -0.000 | 0.845 | 15.0 | 31.0 |
| 0.400 | 0.600 | 0.200 | 0.200 | 0.002 | 0.826 | -0.001 | 0.822 | 18.0 | 31.0 |
| 0.300 | 0.600 | 0.200 | 0.400 | 0.002 | 0.841 | -0.000 | 0.839 | 17.0 | 31.0 |

**VALIDATION'da J' > 0 olan aday YOK → dondurulacak config yok (YENİ sistem kabul edilmez).**