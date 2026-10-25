import subprocess
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from camera_tracker.api import create_app


def test_dashboard_prefers_a_product_with_collected_quotes() -> None:
    dashboard = Path(__file__).resolve().parents[1] / "src" / "camera_tracker" / "web" / "index.html"
    content = dashboard.read_text(encoding="utf-8")

    assert "const overviewRows = await drawOverview();" in content
    assert "select.value = overviewRows[0].product_id;" in content


def test_dashboard_offers_jd_public_price_adapter() -> None:
    dashboard = Path(__file__).resolve().parents[1] / "src" / "camera_tracker" / "web" / "index.html"

    assert '<option>jd</option>' in dashboard.read_text(encoding="utf-8")
    assert '<option>browser_jd</option>' in dashboard.read_text(encoding="utf-8")


def test_dashboard_groups_merchant_source_health_and_has_responsive_metric_layout() -> None:
    dashboard = Path(__file__).resolve().parents[1] / "src" / "camera_tracker" / "web" / "index.html"
    content = dashboard.read_text(encoding="utf-8")

    assert "groupSourceRows" in content
    assert '<details class="source-group"' in content
    assert "#metrics { display: grid" in content
    assert "@media (max-width: 640px)" in content


def test_wheel_includes_dashboard_asset(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(tmp_path), "."],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(tmp_path.glob("camera_price_tracker-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert "camera_tracker/web/index.html" in archive.namelist()


def test_dashboard_is_served_locally() -> None:
    response = TestClient(create_app()).get("/")

    assert response.status_code == 200
    assert "相机价格监控" in response.text
    assert "/api/products" in response.text
    assert "/api/overview" in response.text
    assert "/api/sources" in response.text
    assert "/api/products/${productId}/forecast" in response.text
    assert "人民币参考价" in response.text
    assert "/api/settings/targets" in response.text
    assert "/api/products/${productId}/comparison" in response.text
    assert "大陆 / 香港比较" in response.text
    assert "/api/used/sony-a1" in response.text
    assert "二手 Sony α1 市场" in response.text
    assert "/api/settings/products/" in response.text
    assert "监控产品设置" in response.text
    assert "/api/settings/sources" in response.text
    assert "采集频率设置" in response.text
    assert "/api/settings/watches" in response.text
    assert "公开监控链接" in response.text
    assert "history-window" in response.text
    assert "24 小时" in response.text
    assert "/api/products/${productId}/events" in response.text
    assert "促销与产品事件" in response.text
    assert "/api/settings/events/" in response.text
    assert "历史低" in response.text
    assert "/api/settings/preferences" in response.text
    assert "购买地区偏好" in response.text
    assert "/api/products/${productId}/metrics" in response.text
    assert "可信价格指标" in response.text
    assert "/api/notifications/test" in response.text
    assert "通知测试" in response.text
    assert "/api/import/csv" in response.text
    assert "手动报价导入" in response.text
