defmodule PdfControlWeb.ReleaseTest do
  use ExUnit.Case, async: false
  import Phoenix.ConnTest
  @endpoint PdfControlWeb.Endpoint
  @release "release-00000000000000000000000000000001"

  test "private release health exposes only bounded counters on loopback" do
    previous = System.get_env("PM_RELEASE_ID")
    System.put_env("PM_RELEASE_ID", @release)

    on_exit(fn ->
      if previous,
        do: System.put_env("PM_RELEASE_ID", previous),
        else: System.delete_env("PM_RELEASE_ID")
    end)

    local = get(build_conn(), "/__pm_release_health")
    assert local.status == 200
    assert Jason.decode!(local.resp_body)["release"] == @release
    assert Jason.decode!(local.resp_body)["ready"]
    foreign = %{build_conn() | remote_ip: {192, 0, 2, 1}} |> get("/__pm_release_health")
    assert foreign.status == 404
    page = get(build_conn(), "/")
    assert Plug.Conn.get_resp_header(page, "x-pm-release") == [@release]
  end

  test "configured public origin permits the HTTPS origin behind the loopback proxy" do
    before = Application.get_env(:pdf_control_web, :public_origin)
    Application.put_env(:pdf_control_web, :public_origin, "https://rpdf.dichfoto.com")

    on_exit(fn ->
      if before,
        do: Application.put_env(:pdf_control_web, :public_origin, before),
        else: Application.delete_env(:pdf_control_web, :public_origin)
    end)

    conn = build_conn() |> Plug.Conn.put_req_header("origin", "https://rpdf.dichfoto.com")
    assert get(conn, "/api/health").status == 200
  end
end
