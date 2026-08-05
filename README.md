# crowdbasket-CRM

営業リード管理のCRM。単一のHTMLファイルで動作し、データはFirestoreに保存されます。
ビルド手順はありません（外部ライブラリはCDNのFirebaseのみ）。

## 構成

```
crm-deploy/
  index.html    アプリ本体。これ1つで完結
```

`crm-deploy/` は Cloudflare Workers のデプロイ用フォルダと同じ構成にしています。

## 更新のしかた

1. `crm-deploy/index.html` を編集する
2. 同じファイルをデプロイ先の `crm-deploy` フォルダに上書き保存する
3. これまでどおりの手順でデプロイする（Cloudflareダッシュボード、または `wrangler deploy`）
4. 公開URLをスーパーリロード（Ctrl+Shift+R / Cmd+Shift+R）して反映を確認する

デプロイしても既存のクライアントデータはFirestore側にあるため消えません。

## 主な機能

- 新規クライアント / クライアントデータ / 商談 / タスクの管理
- 企業リストの一括取り込み（貼り付け・.xlsx・.csv）と重複検出
- AI判定：Claude が web検索で各社を調べ、ランク・イベント規模・主催者・
  LINE公式アカウントを判定
  - 画面内から実行する方法（Anthropic APIキーを使用。キーは端末にのみ保存）
  - Claude に調べさせたCSVを取り込む方法（「AI調査用の指示文をコピー」から
    指示文を取得して使う）
- 配信リストのCSV書き出し、配信停止の取り込み
