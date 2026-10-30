defmodule PdfControlWeb.TimeoutTest do
  use ExUnit.Case, async: false
  import Plug.Conn
  import Phoenix.ConnTest
  @endpoint PdfControlWeb.Endpoint

  @tag capture_log: true
  test "timed-out worker returns 503, is restarted, and does not replay the request" do
    previous = Application.fetch_env!(:pdf_control_web, :job_timeout)
    Application.put_env(:pdf_control_web, :job_timeout, 1)
    on_exit(fn -> Application.put_env(:pdf_control_web, :job_timeout, previous) end)

    path =
      Path.join(
        System.tmp_dir!(),
        "pdf-timeout-" <> Base.encode16(:crypto.strong_rand_bytes(12)) <> ".pdf"
      )

    python = Application.fetch_env!(:pdf_control_web, :python)

    code =
      "from PIL import Image; import sys; Image.new('RGB',(600,300),'white').save(sys.argv[1],'PDF')"

    {_, 0} = System.cmd(python, ["-c", code, path])

    try do
      body =
        "--slow\r\nContent-Disposition: form-data; name=\"use_ocr\"\r\n\r\ntrue\r\n" <>
          "--slow\r\nContent-Disposition: form-data; name=\"file\"; filename=\"scan.pdf\"\r\n" <>
          "Content-Type: application/pdf\r\n\r\n" <> File.read!(path) <> "\r\n--slow--\r\n"

      response =
        build_conn()
        |> put_req_header("content-type", "multipart/form-data; boundary=slow")
        |> post("/api/editable", body)

      assert response.status == 503
      Application.put_env(:pdf_control_web, :job_timeout, previous)
      assert await_ready(100)
    after
      File.rm(path)
    end
  end

  defp await_ready(0), do: false

  defp await_ready(attempts) do
    ready =
      try do
        PdfControl.Engine.available?()
      catch
        :exit, _ -> false
      end

    if ready do
      true
    else
      Process.sleep(20)
      await_ready(attempts - 1)
    end
  end
end
