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

ブラウザで `http://localhost:5000` を開き、画像を選択して「背景を削除（輪郭抽出）」を押します。処理後にプレビュー下の「高画質版をダウンロード」または「軽量版をダウンロード」を押してください。元画像の下のボタンで左右90°に回転でき、回転後の向きで背景除去します。高画質版は安全リサイズ後の解像度（長辺2500px以下）、軽量版は縦横比を保って最大200pxに縮小し、最大64色に減色した透過パレットPNG（PNG8）です。RGBA対応のFASTOCTREEでアルファ情報をパレットに保持し、PNG最適化で容量を削減します。容量のための追加縮小は行いません。減色によって色や半透明部分の階調は近似されます。小さい画像は拡大しません。ファイル名は `元のファイル名_original.png` と `元のファイル名_lite.png` で区別できます。

初回の背景除去時に、rembgがU²-Netの標準の高精度な学習済みモデル **u2net**（約176MB）を自動ダウンロードします。CPUで動作します。初回にはインターネット接続とモデル保存先への書き込み権限が必要です。モデルは既定で `~/.u2net` に保存され、以後は再利用されます。`U2NET_HOME` で保存先を変更できます。GitHubのモデル配布先とリダイレクト先へのHTTPSアクセスを許可してください。

20MB・2500万画素によるアプリ側の制限は設けません。長辺2500pxを超える画像は縦横比を保って自動縮小してからRGBA変換・回転・背景除去を行います。JPEGではデコーダー側の縮小も利用します。PNGなどは縮小前のデコードにもメモリが必要で、無制限の巨大画像を保証するものではありません。Pillow標準の極端な画像に対する保護と、公開サーバー側の制限は引き続き適用されます。HEICはサーバーで読み込めますが、ブラウザによっては元画像プレビューが表示できません。細い毛や背景と似た色などは正確に抽出できない場合があります。画像はメモリ上で処理し、アップロード画像や出力をディスクに保存しません。アニメーション・複数ページ画像は先頭フレームを処理します。

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
- `POST /remove-bg`: multipart/form-data の `image` フィールドで画像を送信。任意の `rotation` に右回りの角度（90度単位、既定0）を指定できます。`variants=both` も送信すると、高画質版と軽量版を含むJSONを返します（`original` / `lite` の各オブジェクトに `data_url`、`width`、`height`、`size_bytes`）。`data_url` はBase64エンコードした透過PNGです。従来の利用方法との互換性のため、`variants` を省略すると `image/png` の高画質版を返します。画像未選択・不正画像は400、サーバー側のリクエスト制限は413、モデル取得・背景除去エラーは503のJSONレスポンスです。

```bash
curl -f -F image=@photo.jpg http://localhost:5000/remove-bg -o transparent.png
# 両方のPNGを含むJSON
curl -f -F image=@photo.jpg -F variants=both http://localhost:5000/remove-bg -o variants.json
```

`python app.py` は開発用サーバーを起動します。公開運用には本番用WSGIサーバー、HTTPS、認証・レート制限などを別途設定してください。

## テスト

```bash
python -m unittest discover -s tests -v
```

APIの入力検証、容量制限、PNG・アルファチャンネルの返却、高画質版の画素保持、軽量版の縦横比・寸法・容量・小さい画像の非拡大、モデルエラー時の応答を検証します。この単体テストでは推論をモックし、モデルダウンロードは不要です。実モデルの動作確認には起動後に画像をアップロードしてください。

## Google ドライブへの保存

背景除去後の「Google ドライブに保存」は、**軽量版のみ**を設定済みGAS Webアプリへ送信します。Data URLのプレフィックスを除いたBase64と固定ファイル名 `clear_cut_result.png` を、`Content-Type: text/plain` のJSON本文でPOSTします。送信中は二重送信・画像変更・回転を無効化し、JSON応答の `status: "success"` を確認して完了通知を表示します。

保存先フォルダはGAS側の設定に従います。GASには `doPost(e)` で `JSON.parse(e.postData.contents)` を読み、`base64Data` をPNGへ復元して `filename` で指定フォルダに保存し、JSONで結果を返す実装が必要です。Webアプリの公開権限とブラウザから読み取れるCORS応答も必要です。`text/plain` はプリフライトを避けますが、応答のCORS許可まで保証するものではありません。通信・応答確認に失敗した場合は画面にエラーを表示します。重複保存を避けるため、自動再送は行いません。
