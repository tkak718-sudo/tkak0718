# crowdbasket-CRM

営業リード管理のCRM。単一のHTMLファイルで動作し、データはFirestoreに保存されます。
ビルド手順はありません（外部ライブラリはCDNのFirebaseのみ）。

## 構成

```
crm-deploy/
  index.html      アプリ本体。これ1つで完結
wrangler.jsonc    配信設定。crm-deploy/ の中身が公開URLの直下になる
package.json      wrangler のバージョンを固定
```

## 更新のしかた

`main` ブランチが公開中の内容です。**`main` を更新すれば自動で公開されます。**

Cloudflare Workers の Workers Builds がこのリポジトリに繋がっており、`main` への
プッシュを検知して `npx wrangler deploy` を実行します。ファイルを手元にダウンロード
したりアップロードしたりする必要はありません。

1. `crm-deploy/index.html` を編集する
2. `main` にプッシュする
3. Cloudflare の「Deployments」タブに新しいバージョンが増えれば完了
4. 公開URLをスーパーリロード（Ctrl+Shift+R / Cmd+Shift+R）して反映を確認する

デプロイしても既存のクライアントデータはFirestore側にあるため消えません。

### 手元からデプロイする場合

自動デプロイを待たずに反映したいときは、リポジトリのルートで実行します。

```
npm install            # 初回のみ
npx wrangler login     # 初回のみ
npm run deploy
```

配信先の Worker 名は `wrangler.jsonc` の `name` で決まります。ここを変えると別の
URLに新しい Worker が作られてしまうため、変更しないでください。

## 主な機能

- 新規クライアント / クライアントデータ / 商談 / タスクの管理
- 企業リストの一括取り込み（貼り付け・.xlsx・.csv）と重複検出
- AI判定：Claude が web検索で各社を調べ、ランク・イベント規模・主催者・
  LINE公式アカウントを判定
  - 画面内から実行する方法（Anthropic APIキーを使用。キーは端末にのみ保存）
  - Claude に調べさせたCSVを取り込む方法（「AI調査用の指示文をコピー」から
    指示文を取得して使う）
- 配信リストのCSV書き出し、配信停止の取り込み
