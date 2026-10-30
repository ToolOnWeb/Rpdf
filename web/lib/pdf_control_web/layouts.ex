defmodule PdfControlWeb.Layouts do
  use Phoenix.Component

  def root(assigns) do
    ~H"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
      <head>
        {Phoenix.HTML.raw(PdfControlWeb.Assets.head())}
        <meta name="csrf-token" content={Plug.CSRFProtection.get_csrf_token()} />
        <script type="module" src="/liveview.js"></script>
      </head>
      <body>{@inner_content}</body>
    </html>
    """
  end
end

defmodule PdfControlWeb.ErrorHTML do
  def render(template, _assigns), do: Phoenix.Controller.status_message_from_template(template)
end
