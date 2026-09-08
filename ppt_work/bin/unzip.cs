using System;
using System.IO;
using System.IO.Compression;
public static class UnzipShim {
  public static int Main(string[] args) {
    try {
      if (args.Length >= 2 && string.Equals(args[0], "-Z1", StringComparison.OrdinalIgnoreCase)) {
        using (var zip = ZipFile.OpenRead(args[1])) {
          foreach (var entry in zip.Entries) Console.WriteLine(entry.FullName);
        }
        return 0;
      }
      if (args.Length >= 3 && string.Equals(args[0], "-p", StringComparison.OrdinalIgnoreCase)) {
        using (var zip = ZipFile.OpenRead(args[1]))
        using (var input = zip.GetEntry(args[2]).Open())
        using (var output = Console.OpenStandardOutput()) {
          input.CopyTo(output);
          output.Flush();
        }
        return 0;
      }
      Console.Error.WriteLine("Unsupported unzip shim arguments: " + string.Join(" ", args));
      return 2;
    } catch (Exception ex) {
      Console.Error.WriteLine(ex.ToString());
      return 1;
    }
  }
}
