package main
import ("bufio";"fmt";"os";"strconv";"strings";"example.com/tariff")
func main(){ sc:=bufio.NewScanner(os.Stdin); for sc.Scan(){ p:=strings.Split(sc.Text(),"\t"); z,_:=strconv.Atoi(p[0]); w,_:=strconv.ParseFloat(p[1],64); fmt.Println(strconv.FormatFloat(tariff.BasePrice(z,w),'g',-1,64)) } }
