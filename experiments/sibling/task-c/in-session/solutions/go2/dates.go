package main

// Port of libs/weeks/dates.py: add_days, on ISO dates (YYYY-MM-DD).

import "time"

const isoLayout = "2006-01-02"

// addDays is the ISO date the given number of days after iso.
func addDays(iso string, days int) (string, error) {
	d, err := time.Parse(isoLayout, iso)
	if err != nil {
		return "", err
	}
	return d.AddDate(0, 0, days).Format(isoLayout), nil
}

// isoWeek is the ISO week number (1-53) of an ISO date, as in libs/weeks/dates.py.
func isoWeek(iso string) (int, error) {
	d, err := time.Parse(isoLayout, iso)
	if err != nil {
		return 0, err
	}
	_, week := d.ISOWeek()
	return week, nil
}

// toWeekday is the ISO date itself on Monday to Friday, or the following Monday for a Saturday or Sunday.
func toWeekday(iso string) (string, error) {
	d, err := time.Parse(isoLayout, iso)
	if err != nil {
		return "", err
	}
	for d.Weekday() == time.Saturday || d.Weekday() == time.Sunday {
		d = d.AddDate(0, 0, 1)
	}
	return d.Format(isoLayout), nil
}
