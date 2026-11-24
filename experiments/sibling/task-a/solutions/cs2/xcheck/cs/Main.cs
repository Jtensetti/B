using System.Globalization;
using App;
var inv = CultureInfo.InvariantCulture;
string line;
while ((line = Console.ReadLine()) != null) {
  var p = line.Split('\t');
  switch (p[0]) {
    case "geo": Console.WriteLine(Geo.RoadKm(double.Parse(p[1],inv), double.Parse(p[2],inv), double.Parse(p[3],inv), double.Parse(p[4],inv)).ToString("R", inv)); break;
    case "base": Console.WriteLine(Tariff.BasePrice(int.Parse(p[1]), double.Parse(p[2],inv)).ToString("R", inv)); break;
    case "lev": Console.WriteLine(Lev.Distance(p[1], p[2])); break;
    case "wd": Console.WriteLine(App.Calendar.NextWorkday(p[1])); break;
  }
}
