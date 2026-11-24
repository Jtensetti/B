// Package hours parses time-sheet durations. Maintained by the time-reporting team.
package hours

import (
	"errors"
	"strconv"
	"strings"
)

// Parse reads a duration written as H:MM (for example "7:30" or "0:45") and returns hours.
// Minutes must be 00-59. Anything else is an error.
func Parse(text string) (float64, error) {
	parts := strings.Split(strings.TrimSpace(text), ":")
	if len(parts) != 2 || len(parts[1]) != 2 {
		return 0, errors.New("expected H:MM, got " + text)
	}
	h, err := strconv.Atoi(parts[0])
	if err != nil || h < 0 {
		return 0, errors.New("bad hours in " + text)
	}
	m, err := strconv.Atoi(parts[1])
	if err != nil || m < 0 || m > 59 {
		return 0, errors.New("bad minutes in " + text)
	}
	return float64(h) + float64(m)/60.0, nil
}
