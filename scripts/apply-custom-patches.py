#!/usr/bin/env python3
"""
apply-custom-patches.py
在上游 RustDesk 代码基础上应用 RustDesk-Lu 的自定义修改。

修改内容：
1. 恢复「隐藏连接管理窗口」选项
2. 启用 Change ID 功能（不受服务器限制）
3. 跳过 rendezvous server 验证（自建服务器场景）
4. 清除默认 rendezvous server（启动不自动连接）
5. 禁用「启动时检查软件更新」默认勾选
"""
import re
import sys
from pathlib import Path

def patch_file(filepath, patches, label):
    """对单个文件应用多个补丁"""
    p = Path(filepath)
    if not p.exists():
        print(f"  ⚠️  {label}: File not found — {filepath}")
        return False
    content = p.read_text()
    applied = 0
    for old, new, desc in patches:
        if old in content:
            content = content.replace(old, new, 1)
            applied += 1
            print(f"  ✅ {desc}")
        else:
            print(f"  ⚠️  {desc} — pattern not found (already patched or code changed)")
    p.write_text(content)
    return applied > 0

def patch_file_regex(filepath, patterns, label):
    """对单个文件应用正则补丁"""
    p = Path(filepath)
    if not p.exists():
        print(f"  ⚠️  {label}: File not found — {filepath}")
        return False
    content = p.read_text()
    applied = 0
    for pattern, replacement, desc in patterns:
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content, count=1)
            applied += 1
            print(f"  ✅ {desc}")
        else:
            print(f"  ⚠️  {desc} — pattern not found")
    p.write_text(content)
    return applied > 0

def main():
    print("🔧 Applying RustDesk-Lu custom patches...\n")
    total = 0

    # ── 1. src/ipc.rs — 移除 hide_cm 的 pro/custom_client 限制 ──
    print("[1/8] src/ipc.rs")
    ok = patch_file("src/ipc.rs", [(
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
    )], "ipc.rs")
    if ok: total += 1

    # ── 2. desktop_setting_page.dart — 恢复 hide_cm UI ──
    print("\n[2/8] desktop_setting_page.dart")
    ok = patch_file("flutter/lib/desktop/pages/desktop_setting_page.dart", [(
        '            // if (usePassword)\n'
        '            //   hide_cm(!locked).marginOnly(left: _kContentHSubMargin - 6),',

        '            if (usePassword)\n'
        '              hide_cm(!locked).marginOnly(left: _kContentHSubMargin - 6),',

        "Restore hide_cm UI checkbox"
    )], "desktop_setting_page.dart")
    if ok: total += 1

    # ── 3. server_model.dart — 恢复 hideCm 逻辑（5处） ──
    print("\n[3/8] server_model.dart")
    ok = patch_file("flutter/lib/models/server_model.dart", [
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
            '    */\n'
            '\n'
            '    timerCallback() async {',

            '    // initital hideCm at startup\n'
            '    final verificationMethod =\n'
            '        bind.mainGetOptionSync(key: kOptionVerificationMethod);\n'
            '    final approveMode = bind.mainGetOptionSync(key: kOptionApproveMode);\n'
            '    hideCm = option2bool(\n'
            "        'allow-hide-cm', bind.mainGetOptionSync(key: 'allow-hide-cm'));\n"
            "    if (!(approveMode == 'password' &&\n"
            '        verificationMethod == kUsePermanentPassword)) {\n'
            '      hideCm = false;\n'
            '    }\n'
            '\n'
            '    timerCallback() async {',

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
    ], "server_model.dart")
    if ok: total += 1

    # ── 4. config.rs — Change ID + 清空默认服务器 ──
    print("\n[4/8] libs/hbb_common/src/config.rs")
    ok1 = patch_file("libs/hbb_common/src/config.rs", [(
        '    pub fn is_disable_change_id() -> bool {\n'
        '        BUILTIN_SETTINGS\n'
        '            .read()\n'
        '            .unwrap()\n'
        '            .get(keys::OPTION_DISABLE_CHANGE_ID)\n'
        '            .map(|v| v == "Y")\n'
        '            .unwrap_or(false)\n'
        '    }',

        '    pub fn is_disable_change_id() -> bool {\n'
        '        // Force enable change ID feature\n'
        '        false\n'
        '    }',

        "Force enable Change ID (is_disable_change_id → false)"
    )], "config.rs")

    ok2 = patch_file_regex("libs/hbb_common/src/config.rs", [
        (
            r'pub const RENDEZVOUS_SERVERS: &\[&str\] = &\["[^"]*"\];',
            'pub const RENDEZVOUS_SERVERS: &[&str] = &[];',
            "Clear default RENDEZVOUS_SERVERS"
        ),
        (
            r'pub const RS_PUB_KEY: &str = "[^"]+";',
            'pub const RS_PUB_KEY: &str = "";',
            "Clear RS_PUB_KEY"
        ),
    ], "config.rs")
    if ok1 or ok2: total += 1

    # ── 5. common.dart — isChangeIdDisabled 强制 false ──
    print("\n[5/8] flutter/lib/common.dart")
    ok = patch_file("flutter/lib/common.dart", [(
        "bool isChangeIdDisabled() =>\n"
        "    bind.mainGetBuildinOption(key: kOptionDisableChangeId) == 'Y';",

        "bool isChangeIdDisabled() =>\n"
        "    // Force enable change ID feature\n"
        "    false;",

        "isChangeIdDisabled() forced to false"
    )], "common.dart")
    if ok: total += 1

    # ── 6. ui_interface.rs — 跳过 rendezvous server 验证 ──
    print("\n[6/8] src/ui_interface.rs")
    ok = patch_file("src/ui_interface.rs", [(
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

        '    // Skip rendezvous server verification, directly save the custom ID\n'
        '    // This is for self-hosted server scenarios\n'
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
    )], "ui_interface.rs")
    if ok: total += 1


    # ── 7. config.rs — option2bool: disable check-update by default ──
    print("\n[7/8] libs/hbb_common/src/config.rs (option2bool)")
    ok = patch_file("libs/hbb_common/src/config.rs", [(
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
    )], "config.rs (option2bool)")
    if ok: total += 1

    # ── 8. common.dart — option2bool: disable check-update by default ──
    print("\n[8/8] flutter/lib/common.dart (option2bool)")
    ok = patch_file("flutter/lib/common.dart", [(
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
    )], "common.dart (option2bool)")
    if ok: total += 1

    print(f"\n{'='*50}")
    print(f"🎉 Done! Applied patches to {total}/8 files.")
    if total < 8:
        print("⚠️  Some patches could not be applied. Check warnings above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
