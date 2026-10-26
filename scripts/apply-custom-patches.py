#!/usr/bin/env python3
"""
apply-custom-patches.py
在上游 RustDesk 代码基础上应用 RustDesk-Lu 的自定义修改。

六大定制：
1. 恢复「隐藏连接管理窗口」选项（hide_cm）
2. 启用 Change ID 功能（不受服务器限制）
3. 跳过 rendezvous server 验证（自建服务器场景）
4. 清除默认 rendezvous server（启动不自动连接）
5. 禁用「启动时检查软件更新」默认勾选
6. Windows 键盘输入兼容 AutoHotkey 热键

已按上游 v1.5.0 代码核对锚点。任何一处锚点找不到都会打 ⚠️ 并计入失败，
脚本最终以非零退出码结束——同步流水线据此中断构建，绝不静默半打补丁。
"""
import os
import re
import sys
from pathlib import Path

# Ensure we run from the script's directory (repo root)
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

failures = []

def patch_file(filepath, patches, label):
    """对单个文件应用多个补丁（精确字符串替换，每处仅替换第一次命中）"""
    p = Path(filepath)
    if not p.exists():
        print(f"  ❌ {label}: File not found — {filepath}")
        failures.append(f"{label}: file not found")
        return False
    content = p.read_text()
    applied = 0
    for old, new, desc in patches:
        if old in content:
            content = content.replace(old, new, 1)
            applied += 1
            print(f"  ✅ {desc}")
        elif new in content:
            # idempotency sentinel: patch product already present
            applied += 1
            print(f"  ⏭  {desc} — already applied")
        else:
            print(f"  ❌ {desc} — anchor not found")
            failures.append(f"{label}: {desc}")
    p.write_text(content)
    return applied == len(patches)

def patch_file_regex(filepath, patterns, label):
    """对单个文件应用正则补丁；每项可带第 4 元素 already_marker 做幂等检测"""
    p = Path(filepath)
    if not p.exists():
        print(f"  ❌ {label}: File not found — {filepath}")
        failures.append(f"{label}: file not found")
        return False
    content = p.read_text()
    applied = 0
    for item in patterns:
        pattern, replacement, desc = item[:3]
        already = item[3] if len(item) > 3 else None
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content, count=1)
            applied += 1
            print(f"  ✅ {desc}")
        elif already and already in content:
            applied += 1
            print(f"  ⏭  {desc} — already applied")
        else:
            print(f"  ❌ {desc} — pattern not found")
            failures.append(f"{label}: {desc}")
    p.write_text(content)
    return applied == len(patterns)

def main():
    print("🔧 Applying RustDesk-Lu custom patches...\n")
    total = 0

    # ── 1. src/ipc.rs — 移除 hide_cm 的 pro/custom_client 限制 ──
    print("[1/8] src/ipc.rs")
    if patch_file("src/ipc.rs", [(
        '} else if name == "hide_cm" {\n'
        '                    value = if crate::hbbs_http::sync::is_pro() || crate::common::is_custom_client()\n'
        '                    {\n'
        '                        Some(hbb_common::password_security::hide_cm().to_string())\n'
        '                    } else {\n'
        '                        None\n'
        '                    };',

        '} else if name == "hide_cm" {\n'
        '                    value = Some(hbb_common::password_security::hide_cm().to_string());',

        "Remove hide_cm pro/custom_client restriction"
    )], "ipc.rs"): total += 1

    # ── 2. desktop_setting_page.dart — 恢复 hide_cm UI ──
    print("\n[2/8] desktop_setting_page.dart")
    if patch_file("flutter/lib/desktop/pages/desktop_setting_page.dart", [(
        '            // if (usePassword)\n'
        '            //   hide_cm(!locked).marginOnly(left: _kContentHSubMargin - 6),',

        '            if (usePassword)\n'
        '              hide_cm(!locked).marginOnly(left: _kContentHSubMargin - 6),',

        "Restore hide_cm UI checkbox"
    )], "desktop_setting_page.dart"): total += 1

    # ── 3. server_model.dart — 恢复 hideCm 逻辑（5处）──
    # 注意：1.5.0 的字段就是 hideCm（无下划线前缀），直接还原注释块即可。
    print("\n[3/8] server_model.dart")
    if patch_file("flutter/lib/models/server_model.dart", [
        # 3a: setVerificationMethod
        (
            '    await bind.mainSetOption(key: kOptionVerificationMethod, value: method);\n'
            '    /*\n'
            '    if (method != kUsePermanentPassword) {\n'
            '      await bind.mainSetOption(\n'
            "          key: 'allow-hide-cm', value: bool2option('allow-hide-cm', false));\n"
            '    }\n'
            '    */',

            '    await bind.mainSetOption(key: kOptionVerificationMethod, value: method);\n'
            '    if (method != kUsePermanentPassword) {\n'
            '      await bind.mainSetOption(\n'
            "          key: 'allow-hide-cm', value: bool2option('allow-hide-cm', false));\n"
            '    }',

            "Restore setVerificationMethod hideCm reset"
        ),
        # 3b: setApproveMode
        (
            '    await bind.mainSetOption(key: kOptionApproveMode, value: mode);\n'
            '    /*\n'
            "    if (mode != 'password') {\n"
            '      await bind.mainSetOption(\n'
            "          key: 'allow-hide-cm', value: bool2option('allow-hide-cm', false));\n"
            '    }\n'
            '    */',

            '    await bind.mainSetOption(key: kOptionApproveMode, value: mode);\n'
            "    if (mode != 'password') {\n"
            '      await bind.mainSetOption(\n'
            "          key: 'allow-hide-cm', value: bool2option('allow-hide-cm', false));\n"
            '    }',

            "Restore setApproveMode hideCm reset"
        ),
        # 3c: constructor init
        (
            '    /*\n'
            '    // initital _hideCm at startup\n'
            '    final verificationMethod =\n'
            '        bind.mainGetOptionSync(key: kOptionVerificationMethod);\n'
            '    final approveMode = bind.mainGetOptionSync(key: kOptionApproveMode);\n'
            '    _hideCm = option2bool(\n'
            "        'allow-hide-cm', bind.mainGetOptionSync(key: 'allow-hide-cm'));\n"
            "    if (!(approveMode == 'password' &&\n"
            '        verificationMethod == kUsePermanentPassword)) {\n'
            '      _hideCm = false;\n'
            '    }\n'
            '    */',

            '    // initital hideCm at startup\n'
            '    final verificationMethod =\n'
            '        bind.mainGetOptionSync(key: kOptionVerificationMethod);\n'
            '    final approveMode = bind.mainGetOptionSync(key: kOptionApproveMode);\n'
            '    hideCm = option2bool(\n'
            "        'allow-hide-cm', bind.mainGetOptionSync(key: 'allow-hide-cm'));\n"
            "    if (!(approveMode == 'password' &&\n"
            '        verificationMethod == kUsePermanentPassword)) {\n'
            '      hideCm = false;\n'
            '    }',

            "Restore constructor hideCm init (_hideCm → hideCm)"
        ),
        # 3d: updatePasswordModel read
        (
            '    /*\n'
            '    var hideCm = option2bool(\n'
            "        'allow-hide-cm', await bind.mainGetOption(key: 'allow-hide-cm'));\n"
            "    if (!(approveMode == 'password' &&\n"
            '        verificationMethod == kUsePermanentPassword)) {\n'
            '      hideCm = false;\n'
            '    }\n'
            '    */',

            '    var newHideCm = option2bool(\n'
            "        'allow-hide-cm', await bind.mainGetOption(key: 'allow-hide-cm'));\n"
            "    if (!(approveMode == 'password' &&\n"
            '        verificationMethod == kUsePermanentPassword)) {\n'
            '      newHideCm = false;\n'
            '    }',

            "Restore updatePasswordModel hideCm read (renamed to newHideCm)"
        ),
        # 3e: updatePasswordModel compare
        (
            '    /*\n'
            '    if (_hideCm != hideCm) {\n'
            '      _hideCm = hideCm;\n'
            '      if (desktopType == DesktopType.cm) {\n'
            '        if (hideCm) {\n'
            '          await hideCmWindow();\n'
            '        } else {\n'
            '          await showCmWindow();\n'
            '        }\n'
            '      }\n'
            '      update = true;\n'
            '    }\n'
            '    */',

            '    if (hideCm != newHideCm) {\n'
            '      hideCm = newHideCm;\n'
            '      if (desktopType == DesktopType.cm) {\n'
            '        if (newHideCm) {\n'
            '          await hideCmWindow();\n'
            '        } else {\n'
            '          await showCmWindow();\n'
            '        }\n'
            '      }\n'
            '      update = true;\n'
            '    }',

            "Restore updatePasswordModel hideCm compare & window toggle"
        ),
    ], "server_model.dart"): total += 1

    # ── 4. config.rs — Change ID 强制开启 + 清空默认服务器 + 检查更新默认关 ──
    print("\n[4/8] libs/hbb_common/src/config.rs")
    ok_cfg = patch_file("libs/hbb_common/src/config.rs", [
        (
            '    pub fn is_disable_change_id() -> bool {\n'
            '        BUILTIN_SETTINGS\n'
            '            .read()\n'
            '            .unwrap()\n'
            '            .get(keys::OPTION_DISABLE_CHANGE_ID)\n'
            '            .map(|v| v == "Y")\n'
            '            .unwrap_or(false)\n'
            '    }',

            '    pub fn is_disable_change_id() -> bool {\n'
            '        // RustDesk-Lu: force enable change ID feature\n'
            '        false\n'
            '    }',

            "Force enable Change ID (is_disable_change_id → false)"
        ),
        # 检查更新默认关（Rust 侧 option2bool）
        (
            '    if option.starts_with("enable-") {\n'
            '        value != "N"\n'
            '    } else if',

            '    if option.starts_with("enable-") {\n'
            '        // RustDesk-Lu: disable check-update by default\n'
            '        if option == "enable-check-update" {\n'
            '            value == "Y"\n'
            '        } else {\n'
            '            value != "N"\n'
            '        }\n'
            '    } else if',

            "option2bool: enable-check-update defaults to off"
        ),
    ], "config.rs (literal patches)")
    ok_cfg_regex = patch_file_regex("libs/hbb_common/src/config.rs", [
        (
            r'pub const RENDEZVOUS_SERVERS: &\[&str\] = &\["[^"]*"\];',
            'pub const RENDEZVOUS_SERVERS: &[&str] = &[];',
            "Clear default RENDEZVOUS_SERVERS",
            'pub const RENDEZVOUS_SERVERS: &[&str] = &[];',
        ),
        (
            r'pub const RS_PUB_KEY: &str = "[^"]+";',
            'pub const RS_PUB_KEY: &str = "";',
            "Clear RS_PUB_KEY",
            'pub const RS_PUB_KEY: &str = "";',
        ),
    ], "config.rs (regex patches)")
    if ok_cfg and ok_cfg_regex: total += 1

    # ── 5. common.dart — isChangeIdDisabled 强制 false + 检查更新默认关 ──
    print("\n[5/8] flutter/lib/common.dart")
    if patch_file("flutter/lib/common.dart", [
        (
            "bool isChangeIdDisabled() =>\n"
            "    bind.mainGetBuildinOption(key: kOptionDisableChangeId) == 'Y';",

            "bool isChangeIdDisabled() =>\n"
            "    // RustDesk-Lu: force enable change ID feature\n"
            "    false;",

            "isChangeIdDisabled() forced to false"
        ),
        (
            '  if (option.startsWith("enable-")) {\n'
            '    res = value != "N";\n'
            '  } else if',

            '  if (option.startsWith("enable-")) {\n'
            '    // RustDesk-Lu: disable check-update by default\n'
            '    if (option == kOptionEnableCheckUpdate) {\n'
            '      res = value == "Y";\n'
            '    } else {\n'
            '      res = value != "N";\n'
            '    }\n'
            '  } else if',

            "option2bool: enable-check-update defaults to off"
        ),
    ], "common.dart"): total += 1

    # ── 6. ui_interface.rs — 跳过 rendezvous server 验证 ──
    print("\n[6/8] src/ui_interface.rs")
    if patch_file("src/ui_interface.rs", [(
        '    #[cfg(not(any(target_os = "android", target_os = "ios")))]\n'
        '    let rendezvous_servers = crate::ipc::get_rendezvous_servers(1_000).await;\n'
        '    #[cfg(any(target_os = "android", target_os = "ios"))]\n'
        '    let rendezvous_servers = Config::get_rendezvous_servers();\n'
        '\n'
        '    let mut futs = Vec::new();\n'
        '    let err: Arc<Mutex<&str>> = Default::default();\n'
        '    for rendezvous_server in rendezvous_servers {\n'
        '        let err = err.clone();\n'
        '        let id = id.to_owned();\n'
        '        let uuid = uuid.clone();\n'
        '        let old_id = old_id.clone();\n'
        '        futs.push(tokio::spawn(async move {\n'
        '            let tmp = check_id(rendezvous_server, old_id, id, uuid).await;\n'
        '            if !tmp.is_empty() {\n'
        '                *err.lock().unwrap() = tmp;\n'
        '            }\n'
        '        }));\n'
        '    }\n'
        '    join_all(futs).await;\n'
        '    let err = *err.lock().unwrap();\n'
        '    if err.is_empty() {\n'
        '        #[cfg(not(any(target_os = "android", target_os = "ios")))]\n'
        '        crate::ipc::set_config_async("id", id.to_owned()).await.ok();\n'
        '        #[cfg(any(target_os = "android", target_os = "ios"))]\n'
        '        {\n'
        '            Config::set_key_confirmed(false);\n'
        '            Config::set_id(&id);\n'
        '        }\n'
        '    }\n'
        '    err',

        '    // RustDesk-Lu: skip rendezvous server verification, directly save\n'
        '    // the custom ID (for self-hosted server scenarios)\n'
        '    let _ = old_id;\n'
        '    #[cfg(not(any(target_os = "android", target_os = "ios")))]\n'
        '    crate::ipc::set_config_async("id", id.to_owned()).await.ok();\n'
        '    #[cfg(any(target_os = "android", target_os = "ios"))]\n'
        '    {\n'
        '        Config::set_key_confirmed(false);\n'
        '        Config::set_id(&id);\n'
        '    }\n'
        '    ""',

        "Skip rendezvous server verification for custom ID"
    )], "ui_interface.rs"): total += 1

    # ── 7. input_service.rs — Windows 键盘输入兼容 AutoHotkey ──
    # 上游 1.5.0 的 process_chr 已有 `_hotkey` 参数；把 macos+windows 合并块
    # 改为 macOS-only（修字符映射），Windows 落到下方 key_down/key_up，
    # 让 AutoHotkey 能检测 WM_KEYDOWN/WM_KEYUP 的 VK 热键。
    # process_unicode / process_seq 不动（它们没有 hotkey 参数）。
    print("\n[7/8] src/server/input_service.rs (Windows AHK fix)")
    if patch_file("src/server/input_service.rs", [(
        '    #[cfg(any(target_os = "macos", target_os = "windows"))]\n'
        '    if !_hotkey {\n'
        '        if down {\n'
        '            if let Ok(chr) = char::try_from(chr) {\n'
        '                en.key_sequence(&chr.to_string());\n'
        '            }\n'
        '        }\n'
        '        return;\n'
        '    }',

        '    // RustDesk-Lu: on macOS, use key_sequence for non-hotkey character\n'
        '    // input to fix character mapping issues. On Windows, always fall\n'
        '    // through to key_down/key_up so AutoHotkey hotkeys can detect\n'
        '    // WM_KEYDOWN/WM_KEYUP events.\n'
        '    #[cfg(target_os = "macos")]\n'
        '    if !_hotkey {\n'
        '        if down {\n'
        '            if let Ok(chr) = char::try_from(chr) {\n'
        '                en.key_sequence(&chr.to_string());\n'
        '            }\n'
        '        }\n'
        '        return;\n'
        '    }',

        "AHK fix: cfg(macos+windows) block → macOS-only in process_chr"
    )], "input_service.rs"): total += 1

    # ── 8. flutter-build.yml — 禁用 AppImage 构建（pip/appimage-builder 上游已坏）──
    print("\n[8/8] .github/workflows/flutter-build.yml (disable appimage job)")
    if patch_file_regex(".github/workflows/flutter-build.yml", [(
            r'(  build-appimage:\n'
            r'    name: Build appimage \$\{\{ matrix\.job\.target \}\}\n'
            r'    needs: \[build-rustdesk-linux\]\n'
            r'    runs-on: ubuntu-22\.04\n'
            r')    if: \$\{\{ inputs\.upload-artifact \}\}',

            r'\1    if: false  # RustDesk-Lu: appimage-builder pip bug (ignore_egg_info_in_manifest), re-enable upstream fix',

            "Disable AppImage jobs (known-broken packaging dep)",
            "if: false  # RustDesk-Lu: appimage-builder pip bug",
    )], "flutter-build.yml"): total += 1

    print(f"\n{'='*50}")
    if failures:
        print(f"💥 FAILED: {len(failures)} anchor(s) not found — abort, do NOT ship a half-patched build:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    if total == 8:
        print(f"🎉 Done! Applied all patch groups ({total}/8).")
    else:
        print(f"💥 Done but incomplete: {total}/8 patch groups. Aborting.")
        sys.exit(1)

if __name__ == "__main__":
    main()
