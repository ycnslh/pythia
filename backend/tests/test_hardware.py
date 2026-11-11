import hardware


def test_canonical_zone_names():
    assert hardware._canonical_zone_name("BCPU-therm") == "cpu"
    assert hardware._canonical_zone_name("GPU-therm") == "gpu"
    assert hardware._canonical_zone_name("SOC0-therm") == "soc"
    assert hardware._canonical_zone_name("tj") == "tj"
    assert hardware._canonical_zone_name("battery") is None


def test_thermal_zones_are_averaged_per_key(tmp_path, monkeypatch):
    for i, (zone_type, millideg) in enumerate(
        [("BCPU-therm", 40000), ("MCPU-therm", 50000), ("GPU-therm", 60000)]
    ):
        zone = tmp_path / f"thermal_zone{i}"
        zone.mkdir()
        (zone / "type").write_text(zone_type)
        (zone / "temp").write_text(str(millideg))
    monkeypatch.setattr(hardware, "_THERMAL_BASE", tmp_path)

    assert hardware._read_thermal_zones() == {"cpu": 45.0, "gpu": 60.0}


def test_thermal_zones_ignore_out_of_range_sensors(tmp_path, monkeypatch):
    zone = tmp_path / "thermal_zone0"
    zone.mkdir()
    (zone / "type").write_text("cpu-thermal")
    (zone / "temp").write_text("0")
    monkeypatch.setattr(hardware, "_THERMAL_BASE", tmp_path)

    assert hardware._read_thermal_zones() == {}


def test_missing_sysfs_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware, "_THERMAL_BASE", tmp_path / "absent")
    monkeypatch.setattr(hardware, "_JETSON_GPU_LOAD", tmp_path / "absent-gpu")
    assert hardware._read_thermal_zones() == {}
    assert hardware._read_jetson_gpu() is None


def test_jetson_gpu_load_is_scaled(tmp_path, monkeypatch):
    load = tmp_path / "load"
    load.write_text("425")
    monkeypatch.setattr(hardware, "_JETSON_GPU_LOAD", load)
    assert hardware._read_jetson_gpu() == 42.5


async def test_get_metrics_returns_base_fields():
    metrics = await hardware.get_metrics()
    for key in ("cpu", "ram_pct", "ram_total_mb", "disk_pct", "disk_total_gb"):
        assert key in metrics
