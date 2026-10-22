# Testing / 测试

Use a virtual environment with Python 3.12, then install the project and pytest:

```sh
python -m pip install -e . pytest
python -m pytest tests -m "not e2e" -vv --strict-markers
```

The fast checks cover configuration, dependency scanning, script preparation and
UI interactions. Qt uses an offscreen application, so no visible desktop window
is needed. Each test uses a temporary configuration file and does not overwrite
your saved QPyPack preferences.

Real build tests create isolated build environments, download build tools and
execute the resulting CLI programs. They need network access and, for Nuitka,
a working platform C compiler/toolchain:

```sh
python -m pip install pyinstaller nuitka zstandard
python -m pytest tests -m e2e -vv --strict-markers
```

Without Nuitka installed, its test is reported as skipped, not passed. The CI
build-test job installs it explicitly. Running pytest without a marker filter
runs both the fast checks and real build tests.

The `CI` workflow runs fast checks on Linux, Windows and macOS with Python 3.12
for pull requests and pushes to `main`. After those checks pass, it runs both
real build tests on all three platforms. You can also start the full workflow
with **Actions → CI → Run workflow**. These checks do not publish releases or packages.

## 中文说明

在 Python 3.12 虚拟环境中运行上述命令。`-m "not e2e"` 执行快速检查；
`-m e2e` 执行真正的打包和产物运行验证，需要联网，Nuitka 还需要 C 编译工具链。
测试配置使用临时文件，不覆盖个人设置。未安装 Nuitka 时会明确显示跳过。

PR 和主分支提交先自动执行三平台快速检查，通过后在三平台执行两种引擎的真实编译验证。
也可以通过 Actions 页面手动运行完整流程。
这只是 Python 3.12 的验证范围，不代表已验证项目声明的所有 Python 版本。
