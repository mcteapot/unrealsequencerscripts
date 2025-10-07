import unreal

def _short_name_from_package(package_path: str) -> str:
    # "/Game/Maps/SubLevels/MySub_A" -> "MySub_A"
    if not package_path:
        return ""
    tail = package_path.rsplit("/", 1)[-1]
    return tail.split(".")[-1]


def _level_short_name(package_path: str) -> str:
    # "/Game/.../PortraitBody_Romantic" -> "PortraitBody_Romantic"
    return unreal.Paths.get_base_filename(package_path or "")


# Helper to add one visibility section
def add_level_visibility_section(track, level_names, visible, start_frame, end_frame, row=0):
    section = track.add_section()
    section.set_row_index(row)                                # stack sections on different rows if they overlap
    section.set_visibility(unreal.LevelVisibility.VISIBLE if visible else unreal.LevelVisibility.HIDDEN)
    # Level names are plain names of streamed sublevels (not package paths)
    section.set_level_names([unreal.Name(n) for n in level_names])
    section.set_range(unreal.FrameNumber(start_frame), unreal.FrameNumber(end_frame))
    return section


def sync_visible_levels_to_sequencer():
    """
    Sync all currently VISIBLE and LOADED streaming sublevels into a Level Visibility track
    on the active Level Sequence, covering the full playback range.
    """
    # 1) Active sequence
    sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
    if not sequence:
        unreal.log_error("No active Level Sequence found. Open a sequence in the editor and try again.")
        return
    unreal.log(f"[Sequencer] Processing: {sequence.get_path_name()}")

    # 2) Find/create Level Visibility track (UE 5.6 style)
    found = sequence.find_tracks_by_type(unreal.MovieSceneLevelVisibilityTrack)
    visibility_track = found[0] if found else sequence.add_track(unreal.MovieSceneLevelVisibilityTrack)
    if not visibility_track:
        unreal.log_error("[Sequencer] Failed to get or create MovieSceneLevelVisibilityTrack.")
        return
    unreal.log(f"[Sequencer] Using Level Visibility Track: {visibility_track.get_name()}")

    # 3) World (non-deprecated API)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    if not world:
        unreal.log_error("Unable to get editor world.")
        return

    levels = unreal.EditorLevelUtils.get_levels(world)
    unreal.log(f"[World] Found {len(levels)} levels in world.")

    visible_level_paths = []
    visible_level_names = []

    # 4) Gather visible+loaded streaming sublevels
    for lvl in levels:
        package_path = lvl.get_package().get_name()  # e.g. "/Game/Maps/SubLevels/MySub_A"
        streaming = unreal.GameplayStatics.get_streaming_level(world, package_path)

        if streaming:
            # Not all streaming classes expose get_world_asset(); avoid calling it.
            is_visible = streaming.is_level_visible()
            is_loaded  = streaming.is_level_loaded()

            # Nice-to-have display name: fall back to short name from package path
            pretty_name = _short_name_from_package(package_path)
            try:
                # If this exists on the specific streaming type, use it
                get_pkg = getattr(streaming, "get_world_asset_package_name", None)
                if callable(get_pkg):
                    pkg_name = get_pkg()  # string path
                    if pkg_name:
                        pretty_name = _short_name_from_package(pkg_name)
            except Exception:
                pass

            #unreal.log(f"[World] Streaming: {pretty_name} | Visible: {is_visible} | Loaded: {is_loaded}")

            if is_visible and is_loaded:
                visible_level_paths.append(package_path)
                short_name = _level_short_name(pretty_name)
                visible_level_names.append(short_name)
        else:
            # Persistent level (no streaming wrapper)
            unreal.log(f"[World] Persistent Level: {package_path}")

    if not visible_level_names:
        unreal.log_warning("[World] No visible, loaded streaming sublevels found to add.")
        return

    unreal.log(f"[World] Visible level paths to sync: {visible_level_names}")

    # 5) Playback range (frames)
    pr = sequence.get_playback_range()
    start_frame = pr.get_start_frame()
    end_frame   = pr.get_end_frame()
    unreal.log(f"[Sequencer] Playback frames: start={start_frame}, end={end_frame}")

    # 6) Avoid duplicates (normalize to strings)
    existing = set()
    for section in visibility_track.get_sections():
        for name_or_path in section.get_level_names():
            existing.add(str(name_or_path))

    unreal.log(f"[Sequencer] Existing Level Visibility entries: {sorted(existing)}")

    # 7) Add sections for new visible levels
    ##TODO Switch out the paths 
    added = 0
    for level_path in visible_level_names:
        if level_path in existing:
            unreal.log(f"[Sequencer] Skip (already present): {level_path}")
            continue

        new_section = visibility_track.add_section()
        if not new_section:
            unreal.log_warning(f"[Sequencer] Failed to add section for: {level_path}")
            continue
        new_section.set_row_index(added)
        new_section.set_range(start_frame, end_frame)
        new_section.set_level_names([level_path])               # list[str] or list[SoftObjectPath]
        new_section.set_visibility(unreal.LevelVisibility.VISIBLE)

        added += 1
        unreal.log(f"[Sequencer] Added Level Visibility section for: {level_path}")

    unreal.log_warning(f"[Sequencer] Sync complete. Added {added} new level(s).")

    # 8) Refresh Sequencer UI
    # --- 7) Refresh Sequencer UI ---
    unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()


# --- Run ---
if __name__ == "__main__":
    sync_visible_levels_to_sequencer()
