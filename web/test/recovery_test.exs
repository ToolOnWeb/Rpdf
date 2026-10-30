defmodule PdfControlWeb.RecoveryTest do
  use ExUnit.Case, async: false
  import Plug.Conn
  import Phoenix.ConnTest
  import Phoenix.LiveViewTest
  @endpoint PdfControlWeb.Endpoint

  test "reconnected LiveView restores recent task state without document content" do
    conn = get(build_conn(), "/")
    workspace = get_session(conn, :workspace_id)
    PdfControl.Jobs.publish(workspace, :running)
    assert PdfControl.Jobs.status(workspace) == :running
    {:ok, view, _html} = live(conn)
    assert render(view) =~ "جارٍ معالجة الملف"
    PdfControl.Jobs.publish(workspace, :succeeded)
    assert PdfControl.Jobs.status(workspace) == :succeeded
    assert render(view) =~ "اكتملت المعالجة"
  end

  test "recent task state belongs only to its workspace" do
    one = "one-" <> Base.encode16(:crypto.strong_rand_bytes(16))
    two = "two-" <> Base.encode16(:crypto.strong_rand_bytes(16))
    PdfControl.Jobs.publish(one, :running)
    assert PdfControl.Jobs.status(one) == :running
    assert PdfControl.Jobs.status(two) == nil
  end
end
