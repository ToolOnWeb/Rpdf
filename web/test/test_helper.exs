ExUnit.start()

unless Enum.find(1..150, fn _ ->
         if PdfControl.Engine.available?(),
           do: true,
           else:
             (
               Process.sleep(20)
               false
             )
       end),
       do: raise("PDF worker did not become ready for integration tests")
