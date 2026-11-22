#!/usr/bin/env python3
"""Validate the H436 SpringBoard app-bundle wrapper packaging plan."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/build-h436-springboard-bundle.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    text = BUILD.read_text(encoding="utf-8")
    for marker in (
        "cache.get(\"LaunchDaemons\")",
        '"/System/Library/LaunchDaemons/com.apple.SpringBoard.plist"',
        '"/System/Library/LaunchDaemons/com.apple.lsd.plist"',
        '"/System/Library/CoreServices/SpringBoard.app/SpringBoard"',
        'environment["DYLD_INSERT_LIBRARIES"]',
        '"/private/var/ngpu/lib/SpringBoardSceneObserver.dylib"',
        'environment["DYLD_FORCE_FLAT_NAMESPACE"] = "1"',
        "plistlib.FMT_BINARY",
        '("xpc/launchd.plist"',
        "launchd cache changed unrelated job",
        '("springboard/SpringBoard"',
        '("springboard/SpringBoard.real"',
        "springboard_source.read_bytes()",
        '("xpc/lsdwrap"',
        '("xpc/lsd.real"',
        '("lib/LsdRecoveryAsync.dylib"',
        '"/System/Library/xpc/lsdwrap"',
        'b"build=H585"',
        'b"H540_LS"',
        'b"h541_did_finish_enter"',
        'b"h541_application_state"',
        'b"h542_status_server_bypass_enter"',
        'b"h542_after_did_finish"',
        'b"h543_mc_wait_bypass_enter"',
        'b"h545_cloud_config_ui_bypass"',
        'b"h546_setup_manager_init_enter"',
        'b"h547_by_setup_assistant_needs_to_run_bypass"',
        'b"h548_by_setup_prepare_launch_sentinel_bypass"',
        'b"h549_setup_return_sampler_start"',
        'b"h549_setup_return_main_sample"',
        'b"h550_setup_hud_enter"',
        'b"h550_sound_shared_enter"',
        'b"h550_sound_init_enter"',
        'b"h550_ringer_init_enter"',
        'b"h550_uncaught_exception"',
        'b"h551_status_data_log_empty_init_enter"',
        'b"h551_status_hooks"',
        'b"h552_telephony_shared_enter"',
        'b"h552_telephony_shared_creating_enter"',
        'b"h552_telephony_init_enter"',
        'b"h552_telephony_hooks"',
        'b"h553_application_controller_init_enter"',
        'b"h553_application_library_installed_application_enter"',
        'b"h553_application_library_installed_applications_enter"',
        'b"h553_application_library_all_installed_enter"',
        'b"h553_application_hooks"',
        'b"h554_mutable_set_remove_nil_ignored"',
        'b"h554_mutable_set_remove_guard"',
        'b"h555_concrete_set_remove_guard"',
        'b"h556_post_did_finish_snapshot_enter"',
        'b"h556_post_transaction_flush"',
        'b"h557_startup_hooks"',
        'b"h557_complete_startup_enter"',
        'b"h557_ui_run_enter"',
        'b"h557_post_run_snapshot"',
        'b"h572_observer_loaded"',
        'b"h572_observer_alive"',
        'b"h572_cxx_terminate"',
        'b"h575_cxx_throw"',
        'b"h577_chrono_subscribe_skip"',
        'b"h578_exception_reporters_rearmed"',
        'b"h578_abort_signal"',
        'b"h578_abort_frame"',
        'b"h579_chrono_assertion_stub"',
        'b"h579_chrono_assertion_stub_installed"',
        'b"h580_objc_exception"',
        'b"h581_nsexception"',
        'b"h582_icon_init_exception_caught"',
        'b"h583_complete_startup_exception_caught"',
        'b"h584_chrono_subscribe_skip_return_nil"',
        'b"h585_activity_hooks"',
        'b"h585_bs_proxy_create"',
        'b"h585_bs_message_send_sync_enter"',
        'b"h585_bs_message_send_sync_return"',
        'b"h585_activity_center_init_enter"',
        'b"h585_activity_center_init_return"',
        'b"h585_activity_center_observe_descriptors_enter"',
        'b"h585_activity_center_observe_content_updates_enter"',
        'b"h585_activity_center_observe_reduced_push_budget_enter"',
        'b"h585_activity_authorization_init_enter"',
        'b"methods installed add=independent state="',
        'b"application enumeration skipped"',
        'b"current process proxy skipped"',
        'b"application proxy identifier skipped"',
        'b"application proxy URL skipped"',
        'b"h572_observer_alive sample="',
        '"scripts/add-macho-load-dylib.py"',
        '"/private/var/ngpu/lib/LsdRecoveryAsync.dylib"',
        '"lsd_source_sha256"',
        '"observer_cdhash"',
        '"bootstrap_cdhash"',
        '"springboard_cdhash"',
        '"springboard_observer_load_command"',
        '"lsd_bootstrap_cdhash"',
        '"lsd_recovery_cdhash"',
    ):
        require(marker in text, f"H436 addon builder missing: {marker}")
    require('("daemons/' not in text,
            "H436 must not install LaunchDaemons source files")
    require("fastboot" not in text, "build script must not touch the device")
    require("partition" not in text, "build script must not touch a partition")
    require('"/bin/sh"' not in text, "H436 must not use a shell trampoline")
    print("H436 SpringBoard bundle wrapper packaging gate: PASS")


if __name__ == "__main__":
    main()
