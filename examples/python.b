use py:statistics as stats
fn double(x: Int) -> Int = x * 2
let samples = [double(10), 20, 30]
let average: Float = stats.mean(samples)
print average
