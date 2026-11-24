package main

import "testing"

// Expected results were produced by npm's semver 7.8.5 (satisfies).
func TestSatisfiesMatchesNpm(t *testing.T) {
	cases := []struct {
		version, rng string
		want         bool
	}{
		{"3.0.0", ">=3.0.0", true},
		{"2.9.9", ">=3.0.0", false},
		{"3.1.0-rc.1", ">=3.0.0", false},
		{"3.1.0-rc.1", ">=3.1.0-rc.0", true},
		{"3.1.0-rc.1", ">=3.0.0-rc.0", false},
		{"4.0.0-beta", ">=3.0.0 <4", false},
		{"3.5.1", ">=3.0.0 <4", true},
		{"4.0.0", ">=3.0.0 <4", false},
		{"3.2.0", "^3.1.0", true},
		{"4.0.0", "^3.1.0", false},
		{"3.1.9", "~3.1.0", true},
		{"3.2.0", "~3.1.0", false},
		{"0.2.5", "^0.2.3", true},
		{"0.3.0", "^0.2.3", false},
		{"0.0.3", "^0.0.3", true},
		{"0.0.4", "^0.0.3", false},
		{"3.0.5", ">= 3.0.0", true},
		{"3.0.5", ">3.0.0 || <1", true},
		{"0.5.0", ">3.0.0 || <1", true},
		{"3.0.0", "=3.0.0", true},
		{"v3.0.0", ">=3.0.0", true},
		{"bogus", ">=3.0.0", false},
		{"3.0.0", ">=bogus", false},
		{"3.0.0-alpha", "^3.0.0-alpha", true},
		{"3.0.0", "*", true},
		{"3.0.0-rc", "*", false},
		{"3.0.0", "", true},
	}
	for _, c := range cases {
		if got := satisfies(c.version, c.rng); got != c.want {
			t.Errorf("satisfies(%q, %q) = %v, npm says %v", c.version, c.rng, got, c.want)
		}
	}
}
