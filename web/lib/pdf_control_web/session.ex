defmodule PdfControlWeb.Session do
  import Plug.Conn
  def init(options), do: options

  def call(conn, _options) do
    if get_session(conn, :workspace_id),
      do: conn,
      else:
        put_session(
          conn,
          :workspace_id,
          Base.url_encode64(:crypto.strong_rand_bytes(24), padding: false)
        )
  end
end

defmodule PdfControlWeb.SameOrigin do
  import Plug.Conn
  def init(options), do: options

  def call(conn, _options) do
    origin = get_req_header(conn, "origin")

    expected =
      Application.get_env(:pdf_control_web, :public_origin) ||
        "#{conn.scheme}://#{conn.host}" <>
          if(conn.port in [80, 443], do: "", else: ":#{conn.port}")

    if origin == [] or origin == [expected] do
      conn
    else
      conn |> send_resp(403, "Cross-origin request rejected") |> halt()
    end
  end
end
