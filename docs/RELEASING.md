# Releasing QPyPack

Push a canonical PEP 440 version tag (`v2.9.2`, `v2.9.2rc1`, or
`v2.9.2.dev1`) to start **Build and Publish**. A manual run must select the
same source commit as its existing version tag. It does not create or move tags.

The workflow runs in this order:

1. Run the reusable CI workflow: fast checks and real PyInstaller/Nuitka example
   builds on Linux, Windows and macOS.
2. Validate the tag and stage its version into both package metadata and the app.
3. Build wheel/sdist and native archives. Rebuild the sdist, install both Python
   distributions, and launch their UI outside the checkout. Extract the native
   archives (mount the DMG read-only), launch each frozen UI with its self-check,
   verify version, all translations and icons, render the window and exit cleanly.
4. Collect the complete validated assets, check their source commit and hashes,
   and generate `SHA256SUMS`. Create a draft GitHub Release, upload everything,
   then publish it. Development and prerelease tags produce prereleases.
5. Only in `Qwejay/QPyPack`, publish the already validated Python files through
   the existing PyPI Trusted Publisher. Forks never publish to PyPI. Manual
   upstream runs require the `publish_pypi` checkbox; tag pushes publish automatically.

Fork rehearsals must use development or prerelease tags. They exercise a real
GitHub prerelease, not the production PyPI project. Validation JSON and rendered
windows are retained as `validation-*` Actions artifacts.

macOS builds use ad-hoc signatures. This verifies bundle integrity, but does not
provide Developer ID signing, notarization or a Gatekeeper acceptance guarantee.
Headless startup checks verify packaging and resource loading; they do not replace
interactive testing of all application features or OS versions.

An existing GitHub Release is never overwritten. If creation/upload fails, inspect
the draft and its assets before retrying; remove an unpublished test draft only
after confirming it contains no needed files, or use a new test version. A PyPI
failure can be retried with **Re-run failed jobs**, consuming the same successful
build artifacts; never rebuild and silently replace an already published version.

## 中文说明

发布顺序为：三平台 CI → 构建与安装/启动验证 → 汇总校验 → GitHub Release → PyPI。
Fork 只允许开发版或预发布标签演练，绝不会发布到正式 PyPI。原仓库继续使用既有
Trusted Publisher 配置。已有 Release 不会被覆盖，失败时先检查草稿和产物。
