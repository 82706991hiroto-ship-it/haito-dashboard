// 端末間の同期の接続先(Firebase)。ここに書くのは公開して問題ない識別子だけ。
// データは端末の中で同期コードを鍵に暗号化してから送るので、接続先からは中身を読めない。
// 未設定(null)のあいだは同期の欄に「準備中」と出る。設定の手順は docs/sync-setup.md。
window.HAITO_SYNC_CONFIG = { projectId: "haito-sync", apiKey: "AIzaSyDAHFYvslwfHcu6hXLQ31c7C4CcmIUabbE" };
// 例: window.HAITO_SYNC_CONFIG = { projectId: "haito-sync-xxxxx", apiKey: "AIza...", databaseId: "haito" };
// databaseId は Firestore のデータベースIDに名前を付けたときだけ書く(既定の (default) なら不要)
