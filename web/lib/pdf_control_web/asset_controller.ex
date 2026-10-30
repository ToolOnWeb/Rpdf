defmodule PdfControlWeb.AssetController do
  use Phoenix.Controller, formats: [:html]
  import Plug.Conn

  def css(conn, _),
    do:
      conn
      |> put_resp_content_type("text/css")
      |> send_file(200, PdfControlWeb.Assets.source("app.css"))

  def workspace(conn, _) do
    script =
      "export function mountWorkspace() {\n" <>
        File.read!(PdfControlWeb.Assets.source("app.js")) <> "\n}\n"

    conn |> put_resp_content_type("text/javascript") |> send_resp(200, script)
  end

  def liveview(conn, _) do
    conn
    |> put_resp_content_type("text/javascript")
    |> send_resp(200, """
    import {Socket} from "/vendor/phoenix/phoenix.mjs";
    import {LiveSocket} from "/vendor/liveview/phoenix_live_view.esm.js";
    import {mountWorkspace} from "/workspace.js";
    const Hooks = {PdfWorkspace: {mounted() {
      if (!this.el.dataset.initialized) {
        this.el.dataset.initialized = "true";
        mountWorkspace();
      }
    }}};
    const csrf = document.querySelector('meta[name="csrf-token"]').content;
    const live = new LiveSocket("/live", Socket, {params: {_csrf_token: csrf}, hooks: Hooks});
    live.connect();
    window.pdfControlLive = live;
    """)
  end
end
