# WinMacLink — WindowsとMacのマウス・キーボード共有、Macのリモート操作

WinMacLinkは、WindowsとMacをLANケーブルで直結し、WindowsのマウスとキーボードでMacを操作できる無料ツールです。公開版の操作元はWindows x64です。

- **モニター2台で操作を切り替える。** Windowsの画面端へカーソルを動かすと、隣のMacを同じマウスとキーボードで操作できます。入力共有にはDeskflowを使います。
- **WindowsのウィンドウにMacの画面を表示する。** Windows側からMacのデスクトップを表示し、そのウィンドウ内で操作できます。画面共有にはSSH経由のVNCを使います。

**English:** WinMacLink is a free Windows-to-Mac tool for direct Ethernet connections. Use one keyboard and mouse across two computers with Deskflow, or view and control your Mac desktop in a Windows window via VNC over SSH. The Windows x64 app guides you through connection setup and macOS permissions.

[Windows x64版をダウンロード / Download for Windows x64](https://github.com/ayazukisoma-arch/WinMacLink/releases/latest)

[公式紹介ページ](https://ayazukisoma-arch.github.io/WinMacLink/) · [English overview](https://ayazukisoma-arch.github.io/WinMacLink/en/)

**開発中の0.1版です。全自動セットアップ済みの製品ではありません。** 診断、設定の生成・復元、Windows導入コマンド、Mac用Deskflow導入、SSH経由VNC接続を実装しています。OSの許可、最初の鍵登録、既存設定との統合、起動前ログインや再起動後の実機確認は別工程です。

## GUI

[WinMacLinkの配布ページ（GitHub Releases）](https://github.com/ayazukisoma-arch/WinMacLink/releases)

WindowsでZIPをすべて展開し、展開先の `WinMacLink.exe` をダブルクリックします。起動用のPythonは同梱しています。初回起動でデスクトップにショートカットが作られ、次回からはそのアイコンで開けます。展開先を移動した場合は、移動先で `WinMacLink.exe` をもう一度開いてください。`_internal` と `vendor` は実行ファイルと同じフォルダーに置いてください。

ソースから開く場合は、Python 3.11以降とTkを用意し、ソースのフォルダーで次を実行します。

```powershell
python -m winmaclink gui
```

設定ファイルを選ぶ必要はありません。保存済みの接続先をPC内のアプリ設定から自動で読み込みます。初回はLANの接続履歴から候補を出し、登録画面で不足情報を確認します。既存の開発環境の `.local/profile.json` も自動移行できます。CLIで明示した `--profile` があれば、その設定を優先します。

「Macを探す」はARP接続履歴の候補を表示する機能であり、機器のOSや所有者を認証する機能ではありません。新しいMacが履歴にない場合、Mac側の有線IPの確認が必要です。初回のユーザー名・SSH鍵・ホスト鍵照合・OS許可までは勝手に作成・取得しません。未設定のMacを完全自動で登録できる段階ではありません。

直結モードの候補は有線インターフェース側に絞り、Wi-Fi側のルーターや機器は表示しません。登録済みMacは、キャッシュに情報がなくても登録済みホスト鍵でSSH接続し、macOSの応答を確認します。1台だけ確認できた場合はIP一覧を出さず、そのMacを確認できたことを表示します。認証に失敗した機器は確認済みと扱いません。

「Macを探す」では確認ガイドも開きます。左に「開く順番・見る欄・今回の値」、右に「短いユーザー名・有線IP」の2項目を表示します。Finderの「移動→ホーム」で短いユーザー名、システム設定の「ネットワーク→有線サービス→IPアドレス」で有線IPを確認する手順です。認証済みなら現在のOSと実サービス名に合わせ、初回は未確認表示と画面名の選択を使います。既に認証できている場合のみ、該当するMacの画面を開くボタンも使えます。

SSH鍵の保存先・照合名は通常の登録フォームでは入力しません。ただし登録先の記憶だけで初回認証が完了するわけではありません。鍵の初期準備と本人確認の工程は引き続き実装中です。

診断、セットアップ手順のポップアップ、OS設定画面を開く操作、設定案の確認と保存、画面接続、生成ファイルの復元を操作できます。手順の「次へ」は許可完了の認定ではありません。現版の復元は生成ファイルだけであり、OS設定までの復元はまだ実装していません。

**最初からMacに画面が不要とは保証しません。** 初期設定、Remote Login、画面共有が未設定なら、その許可を与える既存経路が必要です。一時的な画面接続などで初回許可を済ませた後は、1枚のWindowsモニターにVNCを開く運用を目指します。

## できること

「セットアップ → 直結LANの固定IPを設定」から、接続履歴が空でも両機に入れる値を確認できます。Windows側は管理者画面で物理イーサネットを選び、変更内容を確認して `APPLY` を入力すると永続設定を適用します。既存の固定IP、既定経路、別アダプターの重複経路を確認して停止します。以前がDHCPだった対象をこの画面で設定した場合、同じ画面の `RESTORE` でDHCPへ戻せます。Mac側は同じ画面に出る値をMacのTCP/IP設定に入力します。実機での適用・再起動後の再接続は検証待ちです。

- 接続先・ユーザー・鍵の場所・左右上下の配置・直結／LANをプロファイルで指定。
- 読み取り専用の診断：到達性、SSHの信頼／認証エラー、Macの画面共有待受、Deskflowの有無、ファイアウォールの状態。
- 設定を計画→確認→作業フォルダーへ適用。適用はOS設定を書き換えません。
- 元のファイルを記録して復元。利用者の変更があれば、黙って消さずに停止。
- Windows用Deskflow／TigerVNCをwingetから導入。実行は明示的に `--execute` を指定した場合のみ。
- Mac用Deskflow 1.27.0を公式配布元から取得し、固定SHA256とコード署名を検証して導入。既存アプリは変更しません。
- VNCはlocalhost限定のSSHトンネルで接続。ホスト鍵検証を無効化しません。他のプロセスのポートやトンネルを乗っ取りません。

## 始め方

リポジトリのフォルダーをPowerShellで開きます。

```powershell
python -m winmaclink --help
New-Item -ItemType Directory .local -Force
python -m winmaclink init .local/profile.json
```

`.local/profile.json` を自分の接続先へ編集します。例は [examples/profile.example.json](examples/profile.example.json)。パスワードの項目はありません。秘密鍵の内容ではなく、既に用意した鍵のパスを指定します。

初回のホスト鍵は、Macに表示される指紋と照合してOpenSSHへ登録してください。本ツールは `StrictHostKeyChecking=yes` で停止する設計です。新しいIPへ移した同じMacは `host_key_alias` に従来の登録名を指定できます。

```powershell
python -m winmaclink doctor --profile .local/profile.json --output .local/doctor.json
python -m winmaclink plan --profile .local/profile.json --destination .local/staged --output .local/plan.json
# plan.jsonの全内容と変更予定を確認
python -m winmaclink apply --profile .local/profile.json --plan .local/plan.json
python -m winmaclink rollback --destination .local/staged
```

`plan` はファイルの生成計画だけ、`apply` はその生成ファイルの保存だけです。ネットワーク変更、Macへの設定コピー、常駐登録は自動で実行しません。計画後にファイルが変わった場合、適用を拒否します。復元済みのディレクトリを再利用する場合も、記録を保全したうえで新しい出力先を指定してください。

### 導入

```powershell
python -m winmaclink install deskflow
python -m winmaclink install tigervnc
python -m winmaclink install-mac --profile .local/profile.json
# 表示された配布元、変更範囲、ライセンスを確認してから
python -m winmaclink install deskflow --execute
python -m winmaclink install-mac --profile .local/profile.json --execute
```

Windowsはwingetの公式ソースを使用します。配布URLの404、管理者認証、署名・ハッシュ不整合などで失敗した場合、成功扱いにしません。Mac版は既存の `/Applications/Deskflow.app` があればアップグレードしません。初めてのMacへSSH経路を準備する操作は手動です。導入済みアプリやOS権限の取り消しは、生成ファイルの `rollback` の対象外です。

### 画面接続

```powershell
python -m winmaclink connect --profile .local/profile.json
```

フォアグラウンドで動作し、VNCを閉じると自分が作ったSSHトンネルだけを閉じます。認証はビューアーの画面へ入力します。ローカルポートが既に使用されている場合は停止するので、プロファイルの `local_port` を変えてください。

**現版の接続コマンドが対応するのはネイティブTigerVNCです。** フルHDのMac画面をフルHDモニターの「枠付き窓」に等倍表示するとスクロールが必要です。自動縮小は実装済みと扱いません。Java版・RealVNC版などへの自動切替は行いません。

## 現在の制約

- 全OS権限の自動判定、ログイン前の保証、OS設定全体の復元は未実装。GUIは実装していますが、全導入工程の自動化ではありません。
- 初期SSH鍵の作成・信頼登録、Macのアクセシビリティ／ローカルネットワーク／共有の許可は本人の操作が必要。
- 生成したDeskflow設定は**統合前のテンプレート**。証明書の相互確認と既存設定の保全が必要です。`externalConfigFile=layout.conf` は起動ディレクトリを生成先にするか、絶対パスへ設定します。
- 固定IPスクリプトは独立した管理者作業用です。Windows側のローカルアドレス競合チェックだけでルーターや全経路の重複を証明するものではありません。Mac側も既存経路・ネットマスク・サービス名の確認が必要です。実行前に両方の設定を記録してください。
- SSHで暗号化しても、Macの5900番ポートの公開範囲は変わりません。ポート制限・ルーター・IPv6の監査と変更は未実装です。
- 既存アプリをアンインストールしたり、利用中のMacをログアウト／再起動したりしません。
- FileVaultは検出して案内します。Apple Silicon＋macOS 26以降の条件付きSSH解除は候補として表示し、未検証の解除成功を保証しません。無効化は自動で行いません。
- 操作先はローカルIPv4範囲へ制限します。直結モードではMacの有線IPへ接続し、Windows側の指定IPへ送信元を固定します。VPN等を含むOS経路の完全監査は別工程です。公式インストーラー取得だけは明示実行時にインターネットを利用します。

## 検証と開発ループ

```powershell
python -m unittest discover -s tests -v
```

仕様は [docs/SPEC.md](docs/SPEC.md)、実装状況は [docs/LEDGER.md](docs/LEDGER.md)、不具合は [docs/DEFECTS.md](docs/DEFECTS.md)、検証記録は [docs/VALIDATION.md](docs/VALIDATION.md)。安全境界は [SECURITY.md](SECURITY.md) を参照してください。

配布ZIPには、WinMacLinkの実行ファイル、ソースコード、同梱ランタイムのライセンスを収録しています。ビルドする場合は、WindowsでTk付きのPythonと `pyinstaller==6.19.0` を用意し、`python tools/build_windows_release.py` を実行します。実行ファイルのアーキテクチャはビルドに使うPythonに従います。

## 利用条件

原作者の公開名義は綾月想真です。

[WinMacLinkの公式リポジトリ](https://github.com/ayazukisoma-arch/WinMacLink)

WinMacLink本体は、個人でも業務でも無料で利用できます。原版・改変版とも、配布した版のソースコードを無償で入手できるようにし、原作者の表示・公式リポジトリへのリンク・利用条件を残せば無償で再配布できます。改変版はその旨を明記してください。有償での再配布や有償製品への同梱には著作権者の事前の許可が必要です。 [WinMacLinkの利用条件](LICENSE.md)

DeskflowとTigerVNCには各プロジェクトのライセンスが適用されます。TigerVNCはWinGetから個別に取得します。 [Deskflowの公式配布元](https://github.com/deskflow/deskflow/releases/tag/v1.27.0)

「2モニターで入力共有」で承認すると、Windowsから公式版のDeskflowを必要な機種分だけ取得し、SHA-256を照合します。Mac用は直結LANのSSH経由で転送し、Mac上でコード署名も確認します。同じ構成を使い続ける場合は既に導入した版を再利用します。専用のTLS証明書を双方に登録し、Windowsを操作元、Macを操作先として起動します。初回の取得にはWindowsのネット接続が必要です。Windowsでの証明書作成にはOpenSSL、またはGit for Windows付属のOpenSSLが必要です。MacのアクセシビリティなどOSの許可は、求められたときにMac上で承認してください。

Macの入力許可が必要な場合は、WinMacLinkがMacのアクセシビリティ設定を開き、Finderで `deskflow-core` を選択します。Windowsに表示される案内のボタンから、`Deskflow` 本体と `deskflow-core` をそれぞれMacのFinderに表示できます。アクセシビリティの一覧にない項目を、Finderから一覧へドラッグします。Macで両方をオンにすると、WinMacLinkが接続を再試行します。

初回の既定は左です。Macを右に置いている場合は「入力共有でMacへ移る方向」を「右」に変え、「2モニターで入力共有」を押します。同じWinMacLinkウィンドウから切り替えた場合は、そのウィンドウが開始したDeskflow接続を再起動して反映します。

保存済みのMac情報を隠した検証は [docs/BLIND_FIRST_RUN.md](docs/BLIND_FIRST_RUN.md) を参照してください。`python tools/blind_first_run.py` で元の設定を変えずに再現できます。現時点では、初回の自動導入は完了しません。
