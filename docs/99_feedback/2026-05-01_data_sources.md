# ロボエコノミスト データソース設計マスター

**版**: 2026年5月版（初版）
**用途**: プロダクト実装用マスターデータ／シード顧客向け網羅性証跡／業種横展開時のソース追加基盤
**関連ファイル**: `ロボエコノミスト_データソース設計マスター_202605.xlsx`（Excel版・ソート/フィルタ可）

---

## 目次

- [凡例](#凡例)
- [1. 経済統計 — 日本](#1-経済統計--日本)
- [2. 経済統計 — 海外](#2-経済統計--海外)
- [3. 政府系刊行物](#3-政府系刊行物)
- [4. マーケット情報](#4-マーケット情報)
- [5. 業界統計・調査会社](#5-業界統計調査会社)
- [6. 個社IR・開示制度](#6-個社ir開示制度)
- [7. API・自動化実装優先度ロードマップ](#7-api自動化実装優先度ロードマップ)
- [8. 実装コスト・投資見積り](#8-実装コスト投資見積り)

---

## 凡例

**優先度**
- ★★★★★: Standard必須（最低限これがないとプロダクトが成立しない）
- ★★★★: Premium推奨（差別化のため必須）
- ★★★: Enterprise推奨（深掘り分析に必要）
- ★★: 補助（あれば有用）
- ★: 参考

**ティア配置**
- `S` = Standard / `P` = Premium / `E` = Enterprise

**データ形式**
- HTML / PDF / CSV / XBRL / API / RSS / 有料端末（Bloomberg等）

**頻度**
- リアルタイム / 日次 / 週次 / 月次 / 四半期 / 半期 / 年次 / 随時

---

## 1. 経済統計 — 日本

### 1.1 生産・出荷・在庫

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [鉱工業生産指数(IIP)](https://www.meti.go.jp/statistics/tyo/iip/) | 経産省 | 月次 | 月末 | CSV/XBRL | e-Stat API (無料) | 業界需給。電子部品・デバイス内訳が半導体先行指標 | ★★★★★ |
| [供給側主要指標](https://www.meti.go.jp/statistics/tyo/kyoukyu/) | 経産省 | 月次 | 月末 | HTML/CSV | e-Stat API (無料) | 生産動向の補足 | ★★★ |
| [鉱工業出荷内訳表](https://www.meti.go.jp/statistics/tyo/iip/) | 経産省 | 四半期 | 期後1ヶ月 | CSV | e-Stat API (無料) | 在庫循環分析 | ★★★★ |

### 1.2 投資・受注

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [機械受注統計](https://www.esri.cao.go.jp/jp/stat/juchu/juchu.html) | 内閣府 | 月次 | 月中 | PDF/CSV | e-Stat API (無料) | 設備投資先行指標。電気機械が装置需要 | ★★★★★ |
| [建設工事受注動態統計](https://www.mlit.go.jp/toukeijouhou/) | 国交省 | 月次 | 月末 | CSV | e-Stat API (無料) | 半導体工場建設の先行指標 | ★★★★ |
| [建設着工統計](https://www.mlit.go.jp/toukeijouhou/) | 国交省 | 月次 | 月末 | CSV | e-Stat API (無料) | 工場立ち上げの物量的指標 | ★★★ |

### 1.3 景況感・企業

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [日銀短観(TANKAN)](https://www.boj.or.jp/statistics/tk/) | 日銀 | 四半期 | 4月初・7月初・10月初・12月中旬 | HTML/CSV | BOJ時系列統計 (無料) | 業況判断DI・設備投資計画。電気機械・情報通信機械 | ★★★★★ |
| [法人企業景気予測調査](https://www.esri.cao.go.jp/jp/stat/hojin/hojin.html) | 内閣府・財務省 | 四半期 | 四半期直後 | HTML/CSV | e-Stat API (無料) | 大企業の景況判断・売上・利益予想 | ★★★★ |
| [法人企業統計](https://www.mof.go.jp/pri/reference/ssc/) | 財務省 | 四半期 | 期後2-3ヶ月 | HTML/CSV | e-Stat API (無料) | 業種別セグメント業績。同業BS動向構造化の一次データ | ★★★★★ |
| [中小企業景況調査](https://www.shokochukin.co.jp/investigation/) | 商工中金 | 月次 | 月末 | HTML/PDF | なし(スクレイピング) | 中小企業景況感、下請け動向 | ★★★ |
| [景気動向指数(CI/DI)](https://www.esri.cao.go.jp/jp/stat/di/di.html) | 内閣府 | 月次 | 月末 | CSV | e-Stat API (無料) | 景気位置判定(先行・一致・遅行) | ★★★★ |

### 1.4 価格・貿易

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [消費者物価指数(CPI)](https://www.stat.go.jp/data/cpi/) | 総務省 | 月次 | 月中 | CSV | e-Stat API (無料) | インフレ動向 | ★★★★ |
| [企業物価指数(CGPI)](https://www.boj.or.jp/statistics/pi/) | 日銀 | 月次 | 月中 | CSV | BOJ時系列統計 (無料) | 資材コスト、電子部品内訳 | ★★★★★ |
| [貿易統計](https://www.customs.go.jp/toukei/info/) | 財務省 | 月次 | 月中 | CSV/HTML | 税関API (無料) | 半導体等電子部品の輸出動向 | ★★★★★ |
| [国際収支統計](https://www.mof.go.jp/international_policy/reference/) | 財務省・日銀 | 月次 | 月中 | CSV | BOJ時系列統計 (無料) | 経常収支・貿易収支 | ★★★ |

### 1.5 消費・労働

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [消費動向指数(CTI)](https://www.esri.cao.go.jp/jp/stat/shouhi/shouhi.html) | 内閣府 | 月次 | 月末 | HTML | e-Stat API (無料) | 消費者需要 | ★★★ |
| [家計調査](https://www.stat.go.jp/data/kakei/) | 総務省 | 月次 | 月中 | CSV | e-Stat API (無料) | 家計消費、通信・耐久消費財 | ★★★ |
| [有効求人倍率](https://www.mhlw.go.jp/toukei/list/114-1.html) | 厚労省 | 月次 | 月末 | CSV | e-Stat API (無料) | 労働市場逼迫度 | ★★★ |
| [完全失業率](https://www.stat.go.jp/data/roudou/) | 総務省 | 月次 | 月末 | CSV | e-Stat API (無料) | 労働需給 | ★★★ |
| [毎月勤労統計調査](https://www.mhlw.go.jp/toukei/list/30-1.html) | 厚労省 | 月次 | 月中 | CSV | e-Stat API (無料) | 賃金動向、労務単価 | ★★★★ |

### 1.6 サービス・その他

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [サービス産業動向調査](https://www.stat.go.jp/data/mssi/) | 総務省 | 月次 | 月末 | CSV | e-Stat API (無料) | IT・通信サービス動向 | ★★★ |
| [第3次産業活動指数](https://www.meti.go.jp/statistics/tyo/sanzi/) | 経産省 | 月次 | 月末 | CSV | e-Stat API (無料) | サービス業景況 | ★★★ |
| [観光統計](https://www.mlit.go.jp/kankocho/siryou/toukei/) | 観光庁 | 月次 | 月末 | CSV | e-Stat API (無料) | インバウンド消費 | ★★ |

---

## 2. 経済統計 — 海外

### 2.1 米国

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [ISM製造業PMI](https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/) | ISM | 月次 | 月初(第1営業日) | HTML/CSV | なし(スクレイピング) | 景気風向計 | ★★★★★ |
| ISM非製造業PMI | ISM | 月次 | 月初(第3営業日) | HTML/CSV | なし | サービス業景況 | ★★★★ |
| [FRB鉱工業生産(IP)](https://fred.stlouisfed.org/series/INDPRO) | FRB | 月次 | 月中 | CSV | FRED API (無料) | 米国内生産・半導体内訳 | ★★★★ |
| [Durable Goods Orders](https://www.census.gov/manufacturing/m3/) | US Census Bureau | 月次 | 月末 | CSV | Census API (無料) | 耐久財受注、Computers & Electronic Products | ★★★★ |
| [Advance Retail Sales](https://www.census.gov/retail/) | US Census Bureau | 月次 | 月中 | CSV | Census API (無料) | 小売販売、家電・通信機器 | ★★★ |
| [CPI (米国)](https://www.bls.gov/cpi/) | BLS | 月次 | 月中 | CSV | BLS API/FRED (無料) | 米インフレ動向、FED政策予測 | ★★★★ |
| [PCE (米国)](https://www.bea.gov/data/personal-consumption-expenditures-price-index) | BEA | 月次 | 月末 | CSV | BEA API (無料) | FED重視のインフレ指標 | ★★★★ |
| [Nonfarm Payrolls (NFP)](https://www.bls.gov/ces/) | BLS | 月次 | 月初(第1金曜) | CSV | BLS API/FRED (無料) | 米雇用動向 | ★★★★ |
| [JOLTS](https://www.bls.gov/jlt/) | BLS | 月次 | 月中 | CSV | BLS API (無料) | 米労働市場需給 | ★★★ |
| [FOMC議事録](https://www.federalreserve.gov/monetarypolicy/fomcminutes.htm) | FRB | 8回/年 | 会合3週間後 | PDF/HTML | なし(RSS) | 金利パス | ★★★★★ |
| [SEP (Economic Projections)](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) | FRB | 4回/年 | FOMC同時 | PDF | なし | FED経済・金利見通し | ★★★★★ |

### 2.2 中国

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [国家統計局PMI](https://www.stats.gov.cn/) | 国家統計局(NBS) | 月次 | 月末 | HTML/CSV | なし(スクレイピング) | 国有大企業寄り景況 | ★★★★ |
| [Caixin PMI](https://www.caixinglobal.com/) | Caixin/S&P Global | 月次 | 月初 | HTML | 有料API (S&P) | 民間寄り景況 | ★★★★ |
| [工業付加価値・小売総額・固定資産投資](https://www.stats.gov.cn/) | 国家統計局 | 月次 | 月中 | HTML | なし | 中国マクロ動向 | ★★★★ |
| [中国輸出入統計](http://english.customs.gov.cn/) | 税関総署 | 月次 | 月中 | HTML/CSV | なし | 対米・対欧の摩擦影響 | ★★★★ |
| [LPR (貸出プライムレート)](http://www.pbc.gov.cn/) | 中国人民銀行(PBOC) | 月次 | 20日 | HTML | なし | 中国金利パス | ★★★ |
| [中国半導体産業データ](http://www.csia.net.cn/) | CSIA | 月次〜四半期 | 月中 | HTML | なし | 中国半導体業界 | ★★★★ |

### 2.3 台湾

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [月次輸出](https://portal.sw.nat.gov.tw/APGA/GA30) | 財政部 | 月次 | 月初 | HTML/CSV | なし | 半導体輸出動向、世界景気先行 | ★★★★★ |
| [TSMC月次売上](https://investor.tsmc.com/) | TSMC | 月次 | 毎月10日頃 | HTML/PR | IRサイト (無料) | 半導体業界の心拍数 | ★★★★★ |
| [UMC月次売上](https://www.umc.com/en/investors) | UMC | 月次 | 月中 | HTML/PR | IRサイト | ファウンドリ動向 | ★★★★ |
| [MediaTek月次売上](https://corp.mediatek.com/investor-relations) | MediaTek | 月次 | 月中 | HTML/PR | IRサイト | SoC設計動向 | ★★★★ |
| [台湾PMI](https://www.cier.edu.tw/) | CIER(中華経済研究院) | 月次 | 月初 | HTML | なし | 台湾景況 | ★★★ |

### 2.4 韓国

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [月次輸出](https://www.motie.go.kr/) | 産業通商資源部 | 月次 | 月初 | HTML/CSV | なし | 半導体シェア重要、世界景気先行 | ★★★★★ |
| [産業別生産指数](https://kostat.go.kr/) | 統計庁(KOSTAT) | 月次 | 月末 | HTML/CSV | KOSIS API (無料) | 韓国生産動向 | ★★★★ |
| [BOK基準金利](https://www.bok.or.kr/eng/main/main.do) | Bank of Korea | 月次 | MPC決定時 | HTML | なし | 韓国金利パス | ★★★ |
| [Samsung Electronics 予備業績](https://www.samsung.com/global/ir/) | Samsung | 四半期 | 四半期直後(月初) | HTML/PR | IRサイト | 半導体・スマホ動向 | ★★★★★ |
| [SK Hynix業績](https://www.skhynix.com/eng/ir/) | SK Hynix | 四半期 | 四半期直後 | HTML/PR | IRサイト | メモリ業界動向 | ★★★★ |

### 2.5 欧州

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [欧州製造業PMI](https://www.pmi.spglobal.com/) | S&P Global | 月次 | 月初 | HTML | 有料 | 欧州景況 | ★★★ |
| [ECB Economic Bulletin](https://www.ecb.europa.eu/pub/economic-bulletin/) | ECB | 8回/年 | GC会合後2週 | PDF | なし | 欧州マクロ見通し | ★★★★ |
| [ドイツIfoビジネス景況感](https://www.ifo.de/en/survey/ifo-business-climate-index) | Ifo Institute | 月次 | 月末 | HTML | なし | ドイツ景況、車載影響 | ★★★ |
| [EU HICP](https://ec.europa.eu/eurostat/) | Eurostat | 月次 | 月中 | CSV/API | Eurostat API (無料) | 欧州インフレ | ★★★ |
| [ACEA 自動車統計](https://www.acea.auto/) | ACEA | 月次 | 月中 | HTML | なし | 欧州自動車生産、車載CIS | ★★★★ |

### 2.6 グローバル機関

| 指標 | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [IMF/世銀 World Economic Outlook](https://www.imf.org/en/Publications/WEO) | IMF/世銀 | 半期 | 4月・10月 | PDF/API | IMF SDMX API (無料) | 世界マクロ見通し | ★★★ |
| [OECD Economic Outlook](https://www.oecd.org/economic-outlook/) | OECD | 半期 | 5月・11月 | PDF/API | OECD API (無料) | 先進国見通し | ★★★ |

---

## 3. 政府系刊行物

### 3.1 日本 — 経済財政

| 刊行物 | 発行機関 | 頻度 | 公表時期 | 形式 | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [経済財政運営と改革の基本方針(骨太の方針)](https://www5.cao.go.jp/keizai-shimon/) | 内閣府 | 年次 | 6月 | PDF | 中期政策方向性、半導体・DX支援策の重心 | ★★★★★ |
| [成長戦略・新しい資本主義実行計画](https://www.cas.go.jp/jp/seisaku/atarashii_sihonsyugi/) | 内閣官房 | 年次 | 6月 | PDF | 骨太の実行計画 | ★★★★ |
| [経済財政白書](https://www5.cao.go.jp/j-j/wp/) | 内閣府 | 年次 | 8月 | PDF/HTML | 年次経済総括 | ★★★★ |
| [通商白書](https://www.meti.go.jp/report/tsuhaku/) | 経産省 | 年次 | 6-7月 | PDF/HTML | 対中・対米通商政策のシフト | ★★★★ |
| [ものづくり白書](https://www.meti.go.jp/report/whitepaper/mono/) | 経産省 | 年次 | 6月 | PDF/HTML | 製造業動向 | ★★★ |
| [中小企業白書](https://www.chusho.meti.go.jp/pamflet/hakusyo/) | 中小企業庁 | 年次 | 4月 | PDF/HTML | 中小企業動向・サプライチェーン | ★★★ |
| [環境白書・循環型社会白書](https://www.env.go.jp/policy/hakusyo/) | 環境省 | 年次 | 6月 | PDF/HTML | GHG規制・カーボン政策 | ★★★ |
| [労働経済白書](https://www.mhlw.go.jp/wp/hakusyo/roudou/) | 厚労省 | 年次 | 9月 | PDF/HTML | 労働市場動向 | ★★ |

### 3.2 日本 — 産業政策

| 刊行物 | 発行機関 | 頻度 | 公表時期 | 形式 | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [半導体・デジタル産業戦略](https://www.meti.go.jp/policy/mono_info_service/joho/conference/semicon_digital.html) | 経産省 | 随時 | 改訂時 | PDF | 半導体戦略の羅針盤、Rapidus・JASM等 | ★★★★★ |
| [エネルギー基本計画](https://www.enecho.meti.go.jp/category/others/basic_plan/) | 経産省 | 3-4年に1回 | 改訂時 | PDF | エネルギー政策、電力コスト影響 | ★★★★ |
| [GX基本方針](https://www.cas.go.jp/jp/seisaku/gx_jikkou_kaigi/) | 内閣官房 | 年次 | 随時 | PDF | GX/カーボン政策 | ★★★ |
| [国土強靱化基本計画・実施中期計画](https://www.cas.go.jp/jp/seisaku/kokudo_kyoujinka/) | 内閣官房 | 5年に1回 | 改訂時 | PDF | 公共投資見通し | ★★★★★ |
| [宇宙基本計画](https://www8.cao.go.jp/space/) | 内閣府 | 5年に1回 | 改訂時 | PDF | 宇宙関連CIS等 | ★★ |

### 3.3 日本 — 日銀系

| 刊行物 | 発行機関 | 頻度 | 公表時期 | 形式 | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [さくらレポート(地域経済報告)](https://www.boj.or.jp/research/brp/rer/rer.htm) | 日銀 | 四半期 | 1月・4月・7月・10月 | PDF/HTML | 地域経済動向、九州半導体クラスター景況 | ★★★★★ |
| [展望レポート](https://www.boj.or.jp/mopo/outlook/) | 日銀 | 四半期 | 1月・4月・7月・10月 | PDF | 中期経済・物価見通し | ★★★★★ |
| [金融政策決定会合議事要旨](https://www.boj.or.jp/mopo/mpmsche_minu/) | 日銀 | 8回/年 | 会合1ヶ月後 | PDF | 金利パス | ★★★★★ |
| [金融システムレポート](https://www.boj.or.jp/research/brp/fsr/) | 日銀 | 半期 | 4月・10月 | PDF | 金融安定性、信用リスク | ★★★ |

### 3.4 日本 — 投資動向

| 刊行物 | 発行機関 | 頻度 | 公表時期 | 形式 | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [DBJ設備投資計画調査](https://www.dbj.jp/investigate/equip/national/) | 日本政策投資銀行 | 半期 | 6月・12月 | PDF | 業種別設備投資見通し | ★★★★★ |
| [全国企業短期経済観測調査](https://www.boj.or.jp/statistics/tk/) | 日銀 | 四半期 | 上記短観と同じ | HTML/CSV | 設備投資計画付き景況 | ★★★★★ |

### 3.5 海外 — 米国

| 刊行物 | 発行機関 | 頻度 | 公表時期 | 形式 | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [CHIPS Act 関連文書](https://www.chips.gov/) | USDOC | 随時 | 随時 | HTML/PDF | 米半導体産業政策 | ★★★★★ |
| [BIS 輸出規制発表](https://www.bis.doc.gov/) | USDOC/BIS | 随時 | 随時 | HTML/PDF | 対中輸出規制、CIS影響 | ★★★★★ |
| [Fed Beige Book](https://www.federalreserve.gov/monetarypolicy/beigebook/) | FRB | 8回/年 | FOMC 2週前 | PDF/HTML | 米地区連銀景況 | ★★★★ |
| [CBO Economic Outlook](https://www.cbo.gov/publication/60177) | CBO | 年2回 | 1月・8月 | PDF | 米財政見通し | ★★★ |
| [USTR Trade Report](https://ustr.gov/) | USTR | 随時 | 年次+随時 | PDF/HTML | 通商政策 | ★★★ |

### 3.6 海外 — 欧州

| 刊行物 | 発行機関 | 頻度 | 公表時期 | 形式 | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [EU Chips Act](https://digital-strategy.ec.europa.eu/en/policies/european-chips-act) | European Commission | 随時 | 随時 | PDF | 欧州半導体政策 | ★★★★ |
| [CBAM (炭素国境調整メカニズム)](https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism_en) | European Commission | 継続 | 改訂時 | PDF | 炭素関税、CIS製造原価影響 | ★★★ |

### 3.7 海外 — 中国・韓国・台湾

| 刊行物 | 発行機関 | 頻度 | 公表時期 | 形式 | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [五カ年計画(第14次: 2021-2025)](http://www.gov.cn/xinwen/2021-03/13/content_5592681.htm) | 国務院 | 5年に1回 | 改訂時 | HTML/PDF | 中国産業政策 | ★★★★ |
| [政府工作報告](http://www.gov.cn/) | 国務院 | 年次 | 3月全人代 | HTML/PDF | 年次政策 | ★★★★ |
| 中国製造2025 | 国務院 | 継続 | 更新時 | PDF | 産業高度化計画 | ★★★ |
| [K-半導体戦略](https://www.motie.go.kr/) | 産業通商資源部(韓) | 随時 | 改訂時 | PDF | 韓半導体政策 | ★★★ |
| [台湾半導体産業政策](https://www.moea.gov.tw/) | 経済部(台) | 随時 | 改訂時 | PDF | 台湾半導体政策 | ★★★ |

---

## 4. マーケット情報

### 4.1 為替 — 主要ペア

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [USD/JPY](https://jp.tradingeconomics.com/japan/currency) | Bloomberg/LSEG/TradingEconomics | リアルタイム | API/端末 | 有料API | 連結為替換算の主軸 | ★★★★★ |
| [USD/KRW](https://tradingeconomics.com/south-korea/currency) | 同上 | リアルタイム | API/端末 | 有料API | Samsung対比の通貨競争力 | ★★★★★ |
| [USD/TWD](https://tradingeconomics.com/taiwan/currency) | 同上 | リアルタイム | API/端末 | 有料API | TSMC調達コスト | ★★★★ |
| [USD/CNY](https://tradingeconomics.com/china/currency) | 同上 | リアルタイム | API/端末 | 有料API | 中国CIS社との通貨競争 | ★★★★ |
| EUR/JPY | 同上 | リアルタイム | API/端末 | 有料API | 欧州売上・車載 | ★★★ |
| [円実効為替レート](https://www.bis.org/statistics/eer.htm) | BIS | 月次 | CSV | 無料 | 貿易加重実効ベース | ★★★ |
| [名目実効為替レート](https://www.boj.or.jp/statistics/market/forex/) | 日銀 | 月次 | CSV | BOJ時系列統計 (無料) | 国別加重 | ★★★ |
| [BOJ介入履歴・実施](https://www.mof.go.jp/international_policy/reference/feio/) | 日銀・財務省 | 随時 | HTML | 無料 | 円防衛動向 | ★★★ |

### 4.2 金利 — 日本

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [10年国債利回り(JGB)](https://www.mof.go.jp/jgbs/reference/interest_rate/) | 財務省・日本相互証券 | リアルタイム | HTML/API | 無料/有料 | 国内割引率、投資判断 | ★★★★★ |
| 5年国債利回り(JGB) | 同上 | リアルタイム | HTML/API | 無料/有料 | 中期金利 | ★★★★ |
| 20年・30年国債利回り | 同上 | リアルタイム | HTML/API | 無料/有料 | 長期投資評価 | ★★★ |
| [BOJ政策金利](https://www.boj.or.jp/mopo/mpmdeci/mpr_2016/index.htm) | 日銀 | 会合直後 | HTML | 無料 | 短期金利パス | ★★★★★ |
| [BOJオペレーション動向](https://www.boj.or.jp/statistics/boj/fm/ope/index.htm) | 日銀 | 日次 | HTML | 無料 | 国債買入等 | ★★★ |

### 4.3 金利 — 海外

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [10年米国債利回り(UST)](https://fred.stlouisfed.org/series/DGS10) | US Treasury/FRED | リアルタイム | HTML/API | FRED API (無料) | ドル建て割引率 | ★★★★★ |
| 2Y/5Y/30Y UST | 同上 | リアルタイム | API | FRED API (無料) | 米イールドカーブ | ★★★★ |
| [Fed Funds Rate](https://www.federalreserve.gov/monetarypolicy/openmarket.htm) | FRB | 会合直後 | HTML | 無料 | 米短期金利 | ★★★★★ |
| [SOFR](https://www.newyorkfed.org/markets/reference-rates/sofr) | NY Fed | 日次 | CSV | 無料 | ドル資金調達コスト | ★★★★ |
| [韓国国債利回り](https://www.bok.or.kr/eng/main/main.do) | Bank of Korea | 日次 | HTML | 無料 | 韓国資本コスト | ★★★ |
| 台湾・中国国債利回り | 各国中銀 | 日次 | HTML | 有料端末 | 各国資本コスト比較 | ★★★ |

### 4.4 信用スプレッド

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| Corporate Bond Spreads (IG/HY) | Bloomberg/LSEG/ICE | 日次 | 端末 | 有料 | 業界リスクプレミアム | ★★★ |
| CDS Spreads | IHS Markit/S&P | 日次 | 端末 | 有料 | 個社信用リスク | ★★★ |

### 4.5 株式指数

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [TOPIX](https://www.jpx.co.jp/) | JPX | リアルタイム | HTML/API | 有料/無料 | 日本市場ベンチマーク | ★★★★ |
| [日経平均](https://www.nikkei.com/markets/kabu/nk225/) | 日経 | リアルタイム | HTML/API | 有料/無料 | 日本市場ベンチマーク | ★★★★ |
| [東証33業種 電気機器指数](https://www.jpx.co.jp/markets/indices/) | JPX | リアルタイム | HTML/API | 有料/無料 | 業界横比較 | ★★★★★ |
| [SOX指数(フィラデルフィア半導体)](https://www.nasdaq.com/market-activity/index/sox) | Nasdaq | リアルタイム | 端末 | 有料 | 世界半導体ベンチマーク | ★★★★★ |
| Nasdaq Composite | Nasdaq | リアルタイム | HTML/API | 有料/無料 | 米テック指標 | ★★★ |
| [KOSPI](https://www.krx.co.kr/) | Korea Exchange | リアルタイム | HTML/API | 有料/無料 | Samsung/SK比較 | ★★★★ |
| [台湾加権指数(TAIEX)](https://www.twse.com.tw/) | TWSE | リアルタイム | HTML/API | 有料/無料 | TSMC/UMC比較 | ★★★★ |
| [上海総合指数](http://www.sse.com.cn/) | SSE | リアルタイム | HTML/API | 有料/無料 | 中国CIS社比較 | ★★★ |

### 4.6 センチメント指標

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [Nikkei VI](https://indexes.nikkei.co.jp/nkave/index/profile?idx=nk225vi) | JPX | リアルタイム | API | 有料 | 日本ボラティリティ | ★★★ |
| [VIX](https://www.cboe.com/tradable_products/vix/) | CBOE | リアルタイム | API | 有料/無料 | 米ボラティリティ | ★★★ |
| SOX Volatility | Nasdaq | リアルタイム | 端末 | 有料 | 半導体ボラティリティ | ★★★ |

### 4.7 信用格付

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [R&I 格付動向](https://www.r-i.co.jp/) | 格付投資情報センター | 随時 | HTML | 無料閲覧 | 国内格付 | ★★★ |
| [JCR 格付動向](https://www.jcr.co.jp/) | 日本格付研究所 | 随時 | HTML | 無料閲覧 | 国内格付 | ★★★ |
| Moody's/S&P/Fitch | 各社 | 随時 | HTML/端末 | 有料 | グローバル格付 | ★★★ |

### 4.8 商品 — エネルギー・原材料

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [WTI原油](https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm) | NYMEX | リアルタイム | API/端末 | 有料/無料 | エネルギーコスト | ★★★★ |
| Brent原油 | ICE | リアルタイム | API/端末 | 有料/無料 | エネルギーコスト | ★★★★ |
| [銅(LME)](https://www.lme.com/en/Metals/Non-ferrous/LME-Copper) | London Metal Exchange | リアルタイム | API/端末 | 有料 | 電子部品原料 | ★★★ |
| アルミ・ニッケル | LME | リアルタイム | API/端末 | 有料 | 電子部品原料 | ★★★ |
| 金・銀 | COMEX/LME | リアルタイム | API/端末 | 有料/無料 | 貴金属材料 | ★★ |
| [電力先物・LNG](https://www.jepx.jp/) | JEPX/EEX等 | 日次 | 端末 | 有料 | 製造原価 | ★★★★ |

### 4.9 商品 — 半導体関連

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [DRAM Contract Price](https://www.trendforce.com/) | TrendForce/DRAMeXchange | 月次 | HTML | 有料 | メモリ業界需給 | ★★★★★ |
| [NAND Contract Price](https://www.trendforce.com/) | TrendForce | 月次 | HTML | 有料 | メモリ業界需給 | ★★★★★ |
| [メモリスポット価格](https://www.trendforce.com/) | TrendForce | 週次 | HTML | 有料 | 短期価格変動 | ★★★★ |
| [シリコンウェハー価格](https://www.semi.org/) | SEMI/推計 | 四半期 | HTML/推計 | 有料 | ウェハー原価 | ★★★★ |
| 先端プロセスコスト(3nm/2nm) | TechInsights/SemiAnalysis | 随時 | レポート | 有料 | ノード進化コスト | ★★★ |

### 4.10 業界市況指数

| 指標 | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [REIT指数(東証)](https://www.jpx.co.jp/) | JPX | リアルタイム | HTML/API | 有料/無料 | 不動産・金利影響 | ★★★ |
| BDI(バルチック海運指数) | Baltic Exchange | 日次 | 端末 | 有料 | 海運・物流指標 | ★★ |

---

## 5. 業界統計・調査会社

### 5.1 半導体業界団体

| データ | 発行機関 | 頻度 | 公表 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [WSTS世界半導体売上](https://www.wsts.org/) | WSTS | 月次+春秋予測 | 月末+5月・11月 | PDF/HTML | 会員制 | 世界半導体売上、地域別・製品別 | ★★★★★ |
| [SEMI Book-to-Bill Ratio](https://www.semi.org/) | SEMI | 月次 | 月末 | HTML | 会員制 | 装置B/B比、業界景況 | ★★★★★ |
| [SEMI World Fab Forecast](https://www.semi.org/) | SEMI | 四半期 | 四半期 | レポート | 有料会員制 | ファブ設備投資見通し | ★★★★ |
| [SEMI Silicon Shipments](https://www.semi.org/) | SEMI | 四半期 | 四半期後 | PDF | 会員制 | ウェハー出荷量 | ★★★★ |
| [JEITA](https://www.jeita.or.jp/japanese/stat/) | 電子情報技術産業協会 | 月次+年次 | 月末+年次 | HTML | 無料 | 日本電子産業出荷 | ★★★★ |
| [SIA](https://www.semiconductors.org/) | 米半導体工業会 | 月次 | 月末 | HTML | 無料 | 米国基準の世界半導体売上 | ★★★★ |
| [CSIA](http://www.csia.net.cn/) | 中国半導体行業協会 | 月次〜四半期 | 月中 | HTML | 無料 | 中国半導体業界 | ★★★★ |

### 5.2 調査会社 — 半導体・CIS特化

| データ | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [Yole Développement CIS Report](https://www.yolegroup.com/) | Yole Développement | 年次+四半期 | レポート | 有料 | CIS市場・シェア詳細 | ★★★★★ |
| [TechInsights (旧IC Insights)](https://www.techinsights.com/) | TechInsights | 月次+年次 | レポート | 有料 | 半導体詳細分析 | ★★★★ |
| [Omdia (旧IHS Markit)](https://omdia.tech.informa.com/) | Omdia | 四半期 | レポート | 有料 | CIS/半導体・エレクトロニクス | ★★★★★ |
| [SemiAnalysis](https://www.semianalysis.com/) | SemiAnalysis | 随時 | Web/Substack | 有料 | 先端プロセス分析 | ★★★ |

### 5.3 調査会社 — 最終需要

| データ | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [IDC Tracker (スマホ・PC・タブレット)](https://www.idc.com/) | IDC | 四半期+月次 | レポート | 有料 | デバイス出荷 | ★★★★★ |
| [Counterpoint Research](https://www.counterpointresearch.com/) | Counterpoint | 月次+週次+四半期 | レポート | 有料 | スマホシェア詳細 | ★★★★★ |
| [Gartner Market Share](https://www.gartner.com/) | Gartner | 四半期+年次 | レポート | 有料 | PC出荷・IT市場 | ★★★★ |
| [Canalys](https://www.canalys.com/) | Canalys | 四半期 | レポート | 有料 | スマホ・PC市場 | ★★★ |
| [S&P Global Mobility (旧IHS Markit)](https://www.spglobal.com/mobility/) | S&P Global | 月次 | レポート | 有料 | 自動車生産・車載半導体需要 | ★★★★★ |
| [LMC Automotive](https://www.lmc-auto.com/) | LMC Automotive | 月次 | レポート | 有料 | 自動車生産予測 | ★★★★ |

### 5.4 調査会社 — 汎用マクロ・業界

| データ | 発行機関 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|
| [TrendForce (メモリ・半導体)](https://www.trendforce.com/) | TrendForce | 月次〜四半期 | HTML/レポート | 有料 | メモリ価格・スマホ・EV | ★★★★★ |
| [Yano Research (矢野経済研究所)](https://www.yano.co.jp/) | 矢野経済研究所 | 年次+随時 | レポート | 有料 | 日本市場詳細 | ★★★ |
| [富士キメラ総研](https://www.fcr.co.jp/) | 富士キメラ | 年次+随時 | レポート | 有料 | 電子部品市場詳細 | ★★★ |

---

## 6. 個社IR・開示制度

### 6.1 日本

| 制度 | 運営機関 | 対象 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [EDINET (有価証券報告書・四半期報告書)](https://disclosure2.edinet-fsa.go.jp/) | 金融庁 | 日本上場企業 | 年次・四半期 | PDF/XBRL/HTML | EDINET API (無料) | 有報・四半期報告書、経営陣ナラティブ・セグメント情報 | ★★★★★ |
| [TDnet (適時開示)](https://www.release.tdnet.info/) | JPX | 日本上場企業 | リアルタイム | HTML/RSS | JPX API (有料) | 業績修正・M&A・重要事実 | ★★★★★ |
| [EDINET (大量保有報告書)](https://disclosure2.edinet-fsa.go.jp/) | 金融庁 | 5%超保有株主 | 随時 | PDF/XBRL | EDINET API (無料) | アクティビスト検出 | ★★★★ |
| [コーポレートガバナンス報告書](https://www.jpx.co.jp/equities/listed-co/) | JPX | 日本上場企業 | 年次+随時 | PDF/HTML | TDnet経由 | ガバナンス動向 | ★★★ |

### 6.2 米国

| 制度 | 運営機関 | 対象 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [SEC EDGAR (10-K, 10-Q, 8-K)](https://www.sec.gov/edgar) | SEC | 米国上場企業 | 年次・四半期・随時 | HTML/XBRL | EDGAR API (無料) | 米上場企業の全開示 | ★★★★★ |
| [SEC Form 13F (機関投資家保有)](https://www.sec.gov/) | SEC | 1億ドル超運用機関 | 四半期 | HTML/XBRL | EDGAR API (無料) | 機関投資家動向 | ★★★ |

### 6.3 アジア

| 制度 | 運営機関 | 対象 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [DART (韓国電子公示システム)](https://dart.fss.or.kr/) | 金融委員会FSC | 韓国上場企業 | 年次・四半期・随時 | HTML/XBRL | DART API (有料) | Samsung・SK Hynix等 | ★★★★★ |
| [MOPS (台湾市場観測站)](https://mops.twse.com.tw/) | TWSE | 台湾上場企業 | 年次・四半期・随時+月次売上 | HTML | スクレイピング | TSMC・UMC・MediaTek月次売上 | ★★★★★ |
| [HKEXnews (香港)](https://www.hkexnews.hk/) | HKEX | 香港上場企業 | 半年・随時 | HTML/PDF | スクレイピング | SMIC・Xiaomi等 | ★★★★ |
| [SSE(上海)・SZSE(深圳)開示](http://www.sse.com.cn/) | 各証取 | 中国上場企業 | 年次・四半期・随時+月次販売 | HTML/PDF | スクレイピング | OmniVision親会社等の中国CIS社 | ★★★★★ |

### 6.4 欧州

| 制度 | 運営機関 | 対象 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| ESMA GLEIF/OAM (各国オフィシャル開示) | 欧州各国当局 | 欧州上場企業 | 年次・半期 | PDF/XBRL | 各国別 | STMicro等の欧州企業 | ★★★ |

### 6.5 プロフェッショナルソース（有料端末）

| 制度 | 運営機関 | 対象 | 頻度 | 形式 | API | 用途 | 優先度 |
|---|---|---|---|---|---|---|---|
| [Bloomberg Terminal](https://www.bloomberg.com/professional/) | Bloomberg | 全世界 | リアルタイム | 端末+API | 有料 | 全世界データ統合 | ★★★★★ |
| [LSEG Workspace (旧Refinitiv)](https://www.lseg.com/en/data-analytics) | LSEG | 全世界 | リアルタイム | 端末+API | 有料 | 全世界データ統合 | ★★★★★ |
| [FactSet](https://www.factset.com/) | FactSet | 全世界 | リアルタイム | 端末+API | 有料 | コンセンサス予想・分析 | ★★★★ |
| [S&P Capital IQ](https://www.capitaliq.com/) | S&P Global | 全世界 | リアルタイム | 端末+API | 有料 | M&A・PE情報 | ★★★★ |
| [QUICK (日本)](https://corporate.quick.co.jp/) | QUICK | 日本+全世界 | リアルタイム | 端末+API | 有料 | 日本アナリスト予想 | ★★★★ |

---

## 7. API・自動化実装優先度ロードマップ

### 7.1 Phase 1 — Standard基盤（1-3ヶ月で構築）

| ソース | カテゴリ | API種別 | 実装工数 | 取得頻度 | ティア | 備考 |
|---|---|---|---|---|---|---|
| e-Stat統計API | 経済統計(日本) | 無料RESTful API | 1週間 | 月次バッチ | S/P/E | 総務省統計局API。IIP、機械受注等の主要統計を一括取得 |
| BOJ時系列統計データ検索(BOJ-TS) | 経済統計・金利 | 無料API | 1週間 | 月次バッチ | S/P/E | 日銀短観・企業物価指数・為替等 |
| 財務省・税関API | 貿易統計 | 無料API | 3日 | 月次バッチ | S/P/E | 半導体等電子部品輸出動向 |
| FRED API (Federal Reserve) | 経済統計(米) | 無料API | 1週間 | 日次/月次バッチ | S/P/E | 米国マクロデータの標準。GDP・雇用・金利・物価 |
| US BLS API | 経済統計(米) | 無料API | 3日 | 月次バッチ | S/P/E | 米雇用・CPI |
| US Census Bureau API | 経済統計(米) | 無料API | 3日 | 月次バッチ | S/P/E | 米小売・耐久財受注 |
| 為替レート(TradingEconomics等) | マーケット | 有料API(月$50-200) | 1週間 | 日次バッチ | S/P/E | USD/JPY, USD/KRW, USD/TWD, USD/CNY等 |
| 日本国債・米国債利回り(FRED等) | マーケット | 無料/有料API | 3日 | 日次バッチ | S/P/E | 10Y JGB, 10Y UST等 |
| TDnet RSS/フィード | 個社適時開示(日本) | JPX有料API(月数万円〜) | 2週間 | リアルタイム | S/P/E | 重要事実・業績修正のリアルタイム取得 |
| WSTS/SEMI HTML取得 | 業界統計 | スクレイピング | 1週間 | 月次バッチ | S/P/E | 無料公開ページからの取得 |
| TSMC月次売上 | 個社IR | スクレイピング | 3日 | 月次バッチ | S/P/E | 半導体業界心拍数 |
| 台湾・韓国月次輸出 | 経済統計 | スクレイピング | 1週間 | 月次バッチ | S/P/E | 半導体業界先行指標 |

### 7.2 Phase 2 — Premium拡張（3-6ヶ月で構築）

| ソース | カテゴリ | API種別 | 実装工数 | 取得頻度 | ティア | 備考 |
|---|---|---|---|---|---|---|
| EDINET API (有価証券報告書XBRL) | 個社IR(日本) | 無料API | 2週間 | 四半期バッチ | P/E | 有報からセグメント情報・地域別売上を自動抽出 |
| SEC EDGAR API | 個社IR(米) | 無料API | 2週間 | 四半期バッチ | P/E | 米上場企業10-K/10-Qの構造化取得 |
| DART API (韓国) | 個社IR(韓) | 有料API(要登録) | 1ヶ月 | 四半期バッチ | P/E | Samsung・SK Hynix |
| MOPS スクレイピング(台湾) | 個社IR(台) | スクレイピング | 2週間 | 四半期バッチ+月次 | P/E | TSMC・UMC・MediaTek |
| 上海・深圳証取スクレイピング | 個社IR(中) | スクレイピング | 1ヶ月 | 四半期バッチ+月次 | P/E | OmniVision親会社等の中国CIS社 |
| HKEXnews スクレイピング | 個社IR(香港) | スクレイピング | 2週間 | 半年バッチ | P/E | Xiaomi等 |
| Bloomberg/LSEG API 連携 | マーケット総合 | 有料端末API(月$2,000-2,500) | 1ヶ月 | リアルタイム | P/E | 全世界プロフェッショナル統合 |
| Beige Book, FOMC議事録等 PDF解析 | 政府刊行物(米) | スクレイピング+LLM | 2週間 | 8回/年 | P/E | テキスト自動要約 |
| さくらレポート・展望レポート PDF解析 | 政府刊行物(日) | スクレイピング+LLM | 2週間 | 四半期 | P/E | 地域経済テキスト解析 |

### 7.3 Phase 3 — Enterprise深化（6-12ヶ月で構築）

| ソース | カテゴリ | API種別 | 実装工数 | 取得頻度 | ティア | 備考 |
|---|---|---|---|---|---|---|
| TrendForceメモリ価格連携 | 業界統計 | 有料API/データ購入 | 1ヶ月 | 月次/週次 | E | メモリ価格リアルタイム取得 |
| Yole/Omdia CIS詳細データ | 業界統計 | 有料レポート購入+API | 1ヶ月 | 四半期 | E | CIS市場シェア詳細 |
| IDC/Counterpoint スマホデータ | 業界統計 | 有料API | 1ヶ月 | 月次 | E | デバイス出荷リアルタイム |
| S&P Mobility 自動車生産 | 業界統計 | 有料API | 1ヶ月 | 月次 | E | 車載CIS需要予測 |
| 顧客社内データ統合(ERP/BI連携) | 社内データ | カスタム | 3ヶ月 | リアルタイム | E | 顧客毎のカスタム実装 |
| 有報「事業等のリスク」時系列テキスト分析 | 個社IR | LLM独自実装 | 2ヶ月 | 年次 | E | リスクナラティブ変化検出 |
| 業界BS動向構造化(有報XBRL) | 個社IR | EDINET+独自実装 | 2ヶ月 | 四半期 | E | 同業BS動向マップ |
| 業績予想修正の自動反映+ギャップ診断 | 個社IR | TDnet+独自ロジック | 1ヶ月 | リアルタイム | E | 適時開示リアルタイム反映 |
| 経営会議用CXOブリーフ自動生成 | 配信フォーマット | 独自実装+LLM | 2ヶ月 | 月次 | E | 1-2枚の経営層向け要約 |

### 7.4 Phase 4 — 将来拡張（12ヶ月〜）

| ソース | カテゴリ | API種別 | 実装工数 | 取得頻度 | ティア | 備考 |
|---|---|---|---|---|---|---|
| マクロ→個社感応度モデルのバックテスト | モデル | 独自実装 | 3ヶ月 | 四半期 | 全ティア対象 | 過去10年でのモデル精度検証 |
| 業種横展開(不動産・自動車・化学・小売・金融) | プロダクト拡張 | 各業種カスタム | 業種毎3ヶ月 | - | 全ティア対象 | TAM 5-10倍化 |
| グローバル展開(英語版) | プロダクト拡張 | 全面ローカライズ | 6ヶ月 | - | 全ティア対象 | 海外市場開拓 |
| 独自ダッシュボード(Web UI) | プロダクト拡張 | SaaS基盤構築 | 6ヶ月 | - | P/E | loglass超えの経営可視化 |

---

## 8. 実装コスト・投資見積り

| フェーズ | 初期実装費 | 月次運用費（データソース料金合計） | 実装期間 | ティア | 備考 |
|---|---|---|---|---|---|
| Phase 1 (Standard基盤) | 300-500万円 | 月10-30万円 | 1-3ヶ月 | S以上 | 無料APIが大半、TDnet有料+為替API |
| Phase 2 (Premium拡張) | 500-1,000万円 | 月30-80万円 | 3-6ヶ月 | P/E | 海外開示API+Bloomberg等 |
| Phase 3 (Enterprise深化) | 1,000-2,000万円 | 月100-300万円 | 6-12ヶ月 | E | TrendForce/Yole/IDC等有料データ+社内データ統合 |
| Phase 4 (拡張) | 業種毎500-1,000万円 | 業種毎月20-50万円追加 | 業種毎3-6ヶ月 | 全ティア | 業種展開・グローバル・ダッシュボード |

### 8.1 コスト構造の戦略的示唆

- **Standard月30万円の粗利設計**: Phase 1運用費が月10-30万円で、Standardティア月30万円の粗利設計に直結。TDnet有料API・為替APIを除けば大半は無料APIで、実質的にPhase 1はプロダクトの技術的下限を示している。

- **Premium月80万円の利益構造分岐点**: Bloomberg/LSEG連携が月$2,000-2,500（月30-40万円）で、Premium月80万円のうち半分近くがこれに消える計算。ここは顧客数を増やして端末を共有するモデルにしないとスケールしない。

- **Enterprise月200万円の位置付け**: TrendForce/Yole/IDCは1データセット月20-50万円級で、Enterprise月200万円でギリギリ賄える設計。逆に言うとEnterpriseは「顧客ごとに専用データ購入を提供する」という位置付けでしか成立しない。

---

## 更新履歴

| 版 | 更新日 | 主な内容 |
|---|---|---|
| 2026年5月版（初版） | 2026-05-06 | 全8セクション構成で初版作成。半導体・CIS事業を想定した重心配分 |

---

## 関連ドキュメント

- `README.md` — プロジェクト構想サマリー
- `ロボエコノミスト_データソース設計マスター_202605.xlsx` — Excel版（ソート/フィルタ可）
- `建設セクター月次レポート_202605.xlsx` — 建設5社月次セクターレポート
- `半導体セクター月次レポート_202605.xlsx` — 半導体5社月次セクターレポート
- `半導体ロボエコノミスト_TAM_アタックリスト.xlsx` — 市場サイジング＋価格ティア＋アタックリスト
- `ロボエコノミスト_経営企画部向けデモ_202605.pptx` — シード3社向けデモデッキ
