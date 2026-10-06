# ClearCut — 画像背景除去

Flask・rembg・PillowとHTML/CSS/Vanilla JavaScriptによるWebアプリです。画像の被写体を自動認識し、周囲の背景を除去した透過PNGをダウンロードできます。ドラッグ＆ドロップ、元画像との比較、チェッカー柄による透過表示、HEIC/HEIF入力に対応します。

## 起動方法

Python 3.11以上（3.12推奨）を使用してください。

```bash
cd image-bg-remober  # このリポジトリを配置したディレクトリ
python -m venv .venv
source .venv/bin/activate
# Windowsでは .venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

ブラウザで `http://localhost:5000` を開き、画像を選択して「背景を削除（輪郭抽出）」を押します。処理後に「透過PNGをダウンロード」を押してください。

初回の背景除去時に、rembgがU²-Netの標準の高精度な学習済みモデル **u2net**（約176MB）を自動ダウンロードします。CPUで動作します。初回にはインターネット接続とモデル保存先への書き込み権限が必要です。モデルは既定で `~/.u2net` に保存され、以後は再利用されます。`U2NET_HOME` で保存先を変更できます。GitHubのモデル配布先とリダイレクト先へのHTTPSアクセスを許可してください。

画像は20MB・2500万画素までです。HEICはサーバーで読み込めますが、ブラウザによっては元画像プレビューが表示できません。細い毛や背景と似た色などは正確に抽出できない場合があります。画像はメモリ上で処理し、アップロード画像や出力をディスクに保存しません。アニメーション・複数ページ画像は先頭フレームを処理します。

## 構成

```text
image-bg-remober/
├── app.py
├── requirements.txt
├── .gitignore
├── README.md
└── templates/
    └── index.html
```

リポジトリ名の `remober` は既存の名前を使用しています。任意のディレクトリ名（例: `image-bg-remover`）でも起動できます。

## API

- `GET /`: アップロード・比較画面。
- `POST /remove-bg`: multipart/form-data の `image` フィールドで画像を送信。成功時は `image/png` の透過PNGを返します。画像未選択・不正画像は400、サイズ超過は413、モデル取得・背景除去エラーは503のJSONレスポンスです。

```bash
curl -f -F image=@photo.jpg http://localhost:5000/remove-bg -o transparent.png
```

`python app.py` は開発用サーバーを起動します。公開運用には本番用WSGIサーバー、HTTPS、認証・レート制限などを別途設定してください。

## テスト

```bash
python -m unittest discover -s tests -v
```

APIの入力検証、容量制限、PNG・アルファチャンネルの返却、モデルエラー時の応答を検証します。この単体テストでは推論をモックし、モデルダウンロードは不要です。実モデルの動作確認には起動後に画像をアップロードしてください。
