defmodule PdfControlWeb.Assets do
  def source(name),
    do:
      Path.join([
        Application.fetch_env!(:pdf_control_web, :source_root),
        "src/pdf_control/static",
        name
      ])

  def html do
    File.read!(source("index.html"))
  end

  def head do
    [_, head] = Regex.run(~r/<head>(.*?)<\/head>/s, html())
    head
  end

  def body do
    [_, body] = Regex.run(~r/<body>(.*?)<\/body>/s, html())
    Regex.replace(~r/<script\b[^>]*>.*?<\/script>/s, body, "")
  end
end
