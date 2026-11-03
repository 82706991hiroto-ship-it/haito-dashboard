# みんなのランキングを使えるようにする手順(最初の1回だけ・約10分)

同期(docs/sync-setup.md)と同じ Firebase のプロジェクトを使います。無料枠(Sparkプラン)で足ります。

## 仕組み
- 「ランキングに参加する」をオンにした端末だけが、持っている国内株と買い増し候補の**銘柄コードの一覧だけ**を送ります(株数・金額・口座は送りません)。
- 端末は Firebase の匿名ログインで番号をもらい、`poll/{番号}` の1件だけを書き換えます。ルールで自分の分しか書けず、誰も読めません。
- 1日1回、GitHub Actions(`.github/workflows/ranking.yml`)が管理者の鍵で全部を読み、銘柄ごとの人数を `data/ranking.json` に書きます。アプリはこのファイルを読むだけなので、人数が増えても Firebase の読み込みはほとんど増えません。
- 同じ銘柄を選んだ人が10人未満の銘柄は出しません。90日送ってこない端末は数えません。

## 1. 匿名ログインをオンにする
1. https://console.firebase.google.com/ で同期のプロジェクトを開く
2. 左のメニュー「構築」→「Authentication」→「始める」
3. 「Sign-in method」タブ →「匿名」→ 有効にして保存

## 2. ルールを貼り直す
1. 「Firestore Database」→「ルール」タブ
2. 中身をすべて消して、このリポジトリの `firestore.rules` の中身を貼り付け →「公開」(同期の部分はそのまま、`poll` の部分が増えています)

## 3. 集計用の鍵を GitHub に入れる
1. Firebase の歯車 →「プロジェクトの設定」→「サービスアカウント」→「新しい秘密鍵を生成」→ JSON ファイルが保存される
2. GitHub の haito-dashboard リポジトリ →「Settings」→「Secrets and variables」→「Actions」→「New repository secret」
3. Name は `FIREBASE_SA`、Secret に JSON ファイルの中身をすべて貼り付けて保存
4. 保存した JSON ファイルはパソコンから削除する

この鍵はデータベースを読み書きできる鍵です。チャットやメール、リポジトリのファイルには貼らないでください(GitHub の Secrets にだけ入れます)。

データベースに名前を付けた(`(default)` 以外)ときは、同じ画面の「Variables」タブで `FIREBASE_DATABASE` にその名前を入れます。

## 4. 動くか確かめる
1. GitHub の「Actions」→「みんなのランキングの集計」→「Run workflow」
2. 緑になれば完了。以後は毎日朝4時ごろに自動で集計します

## (任意)接続先の識別子の制限
同期の手順6で `apiKey` を「APIの制限」で絞っている場合は、「Identity Toolkit API」と「Token Service API」も許可に加えてください(匿名ログインに使います)。
