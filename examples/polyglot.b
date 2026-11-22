use py:statistics as stats
use net:System.Math as Math
let readings = [3.0, 4.0, 5.0]
let average: Float = stats.mean(readings)
let magnitude: Float = Math.Sqrt(average * average + 9.0)
print magnitude
