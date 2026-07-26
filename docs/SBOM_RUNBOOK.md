# SBOM運用手順

## 目的と境界

`scripts/export_sbom.py` は、リポジトリに固定された `uv.lock` と
`site/package-lock.json` だけを証拠として CycloneDX 1.6 JSON を生成する。レジストリ、
パッケージ配布元、外部APIには接続しない。Python標準ライブラリだけを使用し、生成時刻、
端末名、利用者名、絶対パスを出力しない。

生成物は `artifacts/release-assurance/sbom.cdx.json`。これは依存関係の在庫とロック証拠であり、
脆弱性がないこと、ライセンス利用が適法であること、配布物と実行環境が一致することを単独で
証明するものではない。

## 収録内容

- 固定値 `bomFormat=CycloneDX`、`specVersion=1.6`、`version=1`
- PythonとWebの2つのルートアプリケーション
- `uv.lock` の全解決済みパッケージ、依存辺、PyPI package URL、sdist/wheel URLとSHAハッシュ
- `package-lock.json` の全インストール位置、依存辺、npm package URL、SRIハッシュ、宣言済みlicense
- 両ロックファイルの生バイトに対するSHA-256

npmでは、同一name/versionが複数の `node_modules` 位置に存在できる。package URLは同じでも、
依存解決位置を保持するため `bom-ref` はロック内の相対位置から決定論的に分離する。ロック内の
相対位置そのものはプロパティに保存するが、ワークスペースの絶対パスは保存しない。

## 生成と確認

新規生成:

```bash
uv run python scripts/export_sbom.py
```

既存生成物の確認:

```bash
uv run python scripts/export_sbom.py --check
```

通常生成はexclusive-createであり、既存ファイルを上書きしない。ロック更新後は、差分対象が
正しいことを確認して既存SBOMを明示的に退避または削除し、新規生成する。自動更新のために
上書き処理へ変更してはならない。`--check` は期待するcanonical JSONバイト列をメモリ上で再計算し、
一致を確認するだけで、ファイルを作成・更新しない。欠落またはドリフト時は終了コード1となる。

別の入力・出力を検査する場合:

```bash
uv run python scripts/export_sbom.py \
  --uv-lock path/to/uv.lock \
  --npm-lock path/to/package-lock.json \
  --output path/to/sbom.cdx.json \
  --check
```

## fail-closed条件

次のいずれかを検出すると生成も `--check` も失敗する。

- ロックファイルの欠落、構文不正、未対応lockfile version
- component name/version/sourceの欠落または不正、重複したcomponent identity
- PythonのHTTPS registry以外のsource、`.` 以外のeditable source
- npmの非HTTPS、認証情報、query、fragmentを含むresolved URL
- npmの非bundleパッケージにresolved URLまたはintegrityがない
- 未対応ハッシュ方式、不正な16進数/base64、digest長不一致
- Python配布物にURLまたはhashがない
- 依存名をロック内の単一componentへ解決できない
- npm rootのname/version不一致、非正規な `node_modules` 相対位置
- 生成済みSBOMの欠落、非canonical化、1バイトでも異なるドリフト

現在許可するハッシュは SHA-256、SHA-384、SHA-512。URLのqueryはcredentialでない場合でも拒否する。
秘密を含む署名URLが成果物へ混入する余地を閉じるためである。npmの `inBundle=true` でlockに
resolved/integrityが存在しないcomponentだけは、ハッシュなしのbundle内componentとして収録する。

## 検証

担当範囲の重点テスト:

```bash
uv run pytest tests/test_sbom.py -q
uv run python scripts/export_sbom.py --check
uv run python -m compileall -q scripts/export_sbom.py tests/test_sbom.py
```

テストは決定性、ロック順序への意味的耐性、2 ecosystem、絶対path非依存、欠損・改ざん、
URL credential、依存未解決、exclusive-create、`--check` の非変更性とdrift検出を含む。

## 更新時の確認事項と残余リスク

1. `uv lock --check` と `npm ci`/audit系の別ゲートでロックの整合性を確認する。
2. SBOMを新規生成し、component、version、license、source、hash、依存辺の差分をレビューする。
3. `--check` と重点・全体テストを通し、release-assurance evidenceへ生成物SHAを渡す。
4. 公開判断はSBOMだけでGOにしない。脆弱性監査、secret scan、threat-model review、権利・
   Affiliate・需要・運用実績・Human approvalは別の必須証拠である。

lockfileに記録されないOSライブラリ、Cloudflare実行環境、ブラウザ、ビルド済みbundle内部の完全な
provenanceは対象外である。license文字列はnpm lockの宣言をそのまま記録し、SPDX妥当性やlicense
compatibilityを判定しない。レジストリへ照会しないため、最新脆弱性、撤回済み配布物、publisherの
真正性も評価しない。これらは公開前のdependency audit、provenance確認、Human reviewで補完する。
