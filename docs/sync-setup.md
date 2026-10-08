# 端末間の同期を使えるようにする手順(最初の1回だけ・約10分)

HAITOの「ほかの端末と同期」は、Google の無料サービス Firebase(Cloud Firestore)を置き場所に使います。
データは端末の中で同期コードを鍵に暗号化してから送るので、Firebase(Google)からも中身は読めません。
無料枠(Sparkプラン)で足ります。クレジットカードは要りません。

## 1. Firebase のプロジェクトを作る
1. https://console.firebase.google.com/ を開き、Google アカウントでログイン
2. 「プロジェクトを作成」→ 名前は `haito-sync` など何でもよい
3. 「Google アナリティクス」はオフでよい →「プロジェクトを作成」

## 2. データベース(Cloud Firestore)を作る
1. 左のメニュー「構築」→「Firestore Database」→「データベースを作成」
2. データベースIDは `(default)` のまま。ロケーションは `asia-northeast1 (Tokyo)` を選ぶ(画面の不具合でIDが空のままエラーになるときは、Google Cloud の Firestore 画面から `haito` などの名前で作り、手順5で `databaseId` を書く)
3. 「本番環境モードで開始」を選んで作成

## 3. ルール(誰が読み書きできるか)を貼る
1. Firestore Database の画面上の「ルール」タブを開く
2. 中身をすべて消して、このリポジトリの `firestore.rules` の中身を貼り付け →「公開」

## 4. ウェブアプリを登録して、接続先の識別子をもらう
1. 左上の歯車 →「プロジェクトの設定」→ 下の「マイアプリ」で `</>`(ウェブ)を押す
2. アプリのニックネームは `haito` など →「アプリを登録」(Firebase Hosting はチェック不要)
3. 表示される `firebaseConfig` のうち、`apiKey` と `projectId` の2つを使う

## 5. HAITO に書き込む(GitHub の画面で)
1. GitHub の haito-dashboard リポジトリで `sync-config.js` を開き、鉛筆マーク(Edit)を押す
2. `window.HAITO_SYNC_CONFIG = null;` の行を、次のように書き換える
   ```js
   window.HAITO_SYNC_CONFIG = { projectId: "ここにprojectId", apiKey: "ここにapiKey" };
   ```
   (データベースに名前を付けたときだけ `, databaseId: "haito"` を足す)
   ```
   ```
3. 「Commit changes」で保存。1〜2分でサイトに反映されます

※ `apiKey` は「どのプロジェクトか」を示す公開用の識別子で、パスワードではありません(Firebase の公式説明でも公開してよいものとされています)。
読み書きできる範囲は手順3のルールで決まります。

## 6. (任意)使えるサイトを絞る
Google Cloud コンソール →「APIとサービス」→「認証情報」→ 該当の「Browser key」を開き、
「アプリケーションの制限」を「ウェブサイト」にして `https://82706991hiroto-ship-it.github.io/*` を追加すると、
ほかのサイトからこの識別子を使われにくくなります。

## 使い方
1. 1台目(例: Mac)で「保有銘柄」タブ →「ほかの端末と同期」→「この端末から同期を始める」
2. 表示された同期コード(26文字)をメモに控える
3. 2台目(例: iPhone)で同じ欄の「同期コードを入力する」にコードを入れて「つなぐ」

- 同期コードを知っている人は中身を読めます。人に見せないでください。
- すべての端末でコードを失くすと、誰にも戻せません(各端末に残っているデータは無事です)。
- 2台で同時に別の変更をしたときは、あとから変えた方に合わせます。
