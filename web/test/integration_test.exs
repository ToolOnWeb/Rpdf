defmodule PdfControlWeb.IntegrationTest do
  use ExUnit.Case, async: false
  import Plug.Conn
  import Phoenix.ConnTest
  import Phoenix.LiveViewTest
  @endpoint PdfControlWeb.Endpoint

  test "LiveView serves the complete workspace and receives job state" do
    {:ok, view, html} = live(build_conn(), "/")
    assert html =~ "phx-hook=\"PdfWorkspace\""
    assert html =~ "pdf-control-theme"
    assert html =~ "editor-output-name"
    send(view.pid, {:job, :running})
    assert render(view) =~ "جارٍ معالجة الملف"
  end

  test "same-origin boundary rejects foreign-origin API requests" do
    conn =
      build_conn()
      |> put_req_header("origin", "https://foreign.invalid")
      |> put_req_header("content-type", "text/plain")
      |> post("/api/info", "")

    assert conn.status == 403
  end

  test "API validation and headers survive the Phoenix worker boundary" do
    conn =
      build_conn() |> put_req_header("content-type", "multipart/form-data; boundary=pdf-test")

    body =
      "--pdf-test\r\nContent-Disposition: form-data; name=\"file\"; filename=\"bad.pdf\"\r\nContent-Type: application/pdf\r\n\r\ninvalid\r\n--pdf-test--\r\n"

    result = post(conn, "/api/info", body)
    assert result.status == 400
    assert get_resp_header(result, "content-type") |> hd() =~ "application/json"
    assert Jason.decode!(result.resp_body)["detail"] =~ "PDF"
  end

  test "all frontend modules and original styles are served locally" do
    assert get(build_conn(), "/liveview.js").resp_body =~ "LiveSocket"
    assert get(build_conn(), "/workspace.js").resp_body =~ "export function mountWorkspace"
    assert get(build_conn(), "/app.css").status == 200
    assert get(build_conn(), "/vendor/phoenix/phoenix.mjs").status == 200
    assert get(build_conn(), "/vendor/liveview/phoenix_live_view.esm.js").status == 200
  end

  test "health remains independent of CPU processing paths" do
    result = get(build_conn(), "/api/health")
    assert Jason.decode!(result.resp_body)["interface"] == "liveview"
    assert result.status == 200
  end
end
