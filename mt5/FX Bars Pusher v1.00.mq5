//+------------------------------------------------------------------+
//| FX Bars Pusher v1.00.mq5                                         |
//| Ankush New Vision                                                |
//|                                                                  |
//| CHANGELOG                                                        |
//| v1.00 (2026-11-04)                                               |
//|  - First build. Reads closed M5 bars of one symbol (XAUUSD) and  |
//|    pushes them to GitHub as one JSON file per UTC day:           |
//|    data/XAUUSD/M5/YYYY-MM-DD.json on the "data" branch.         |
//|  - On start: fills the last HistoryDays days (only missing days),|
//|    then re-writes yesterday and today in full.                   |
//|  - After that: every new closed M5 bar re-writes that day's file.|
//|  - NEVER trades. No orders, no position changes.                 |
//|                                                                  |
//| SETUP (once)                                                     |
//|  1. MT5: Tools > Options > Expert Advisors > tick "Allow         |
//|     WebRequest for listed URL" and add https://api.github.com    |
//|  2. GitHub token: fine-grained, ONLY this repo, Contents =       |
//|     Read and write. Type it in the EA inputs. Never in chat.     |
//|  3. Branch "data" must exist in the repo.                        |
//+------------------------------------------------------------------+
#property copyright "Ankush New Vision"
#property version   "1.00"
#property description "Pushes closed M5 bars to GitHub (data branch). Never trades."

input string GitHubToken          = "";                                   // GitHub token (Contents: read+write)
input string GitHubRepo           = "ankushchhajed7-cmd/FX-TRADER-SKILL-"; // owner/repo
input string DataBranch           = "data";                               // branch that receives the bars
input string BrokerSymbol         = "XAUUSDm";                            // symbol name at your broker (Exness: XAUUSDm)
input string FileSymbol           = "XAUUSD";                             // name used in the file path
input int    HistoryDays          = 60;                                   // days of history to fill on start
input int    ServerUtcOffsetHours = 99;                                   // 99 = auto-detect, else fixed hours (server minus UTC)
input int    CheckEverySec        = 10;                                   // how often to look for a new closed bar

string   g_sym        = "";
int      g_offset     = 0;       // server time minus UTC, in seconds
datetime g_lastBar    = 0;       // open time (server) of the last closed bar that was pushed
datetime g_lastDayUtc = 0;       // UTC day start of the last push
int      g_backIdx    = 0;       // backfill counter: HistoryDays ... 2, then 1 (yesterday), then 0 (today)
bool     g_backDone   = false;
datetime g_nextTry    = 0;       // do not retry a failed push before this (local time)
int      g_pushes     = 0;
int      g_fails      = 0;
string   g_lastMsg    = "starting";

//+------------------------------------------------------------------+
int CalcOffset()
  {
   if(ServerUtcOffsetHours != 99)
      return ServerUtcOffsetHours * 3600;
   long diff = (long)(TimeTradeServer() - TimeGMT());
   double steps = MathRound((double)diff / 900.0);   // round to 15 minutes
   return (int)(steps * 900.0);
  }

datetime DayStartUtc(datetime t)
  {
   return (datetime)((long)t - ((long)t % 86400));
  }

string DateStr(datetime utc)
  {
   MqlDateTime d;
   TimeToStruct(utc, d);
   return StringFormat("%04d-%02d-%02d", d.year, d.mon, d.day);
  }

string IsoNow()
  {
   MqlDateTime d;
   TimeToStruct(TimeGMT(), d);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", d.year, d.mon, d.day, d.hour, d.min, d.sec);
  }

string FilePath(datetime dayUtc)
  {
   return "data/" + FileSymbol + "/M5/" + DateStr(dayUtc) + ".json";
  }

string ApiUrl(const string path)
  {
   return "https://api.github.com/repos/" + GitHubRepo + "/contents/" + path;
  }

//+------------------------------------------------------------------+
//| One HTTP call. Returns the HTTP code, or -1 when the call failed |
//+------------------------------------------------------------------+
int Http(const string method, const string url, const string body, string &resp)
  {
   char   post[];
   char   out[];
   string rh = "";
   string headers = "Authorization: Bearer " + GitHubToken + "\r\n" +
                    "Accept: application/vnd.github+json\r\n" +
                    "User-Agent: FXBarsPusher\r\n" +
                    "X-GitHub-Api-Version: 2022-11-28\r\n" +
                    "Content-Type: application/json\r\n";
   if(StringLen(body) > 0)
     {
      StringToCharArray(body, post, 0, WHOLE_ARRAY, CP_UTF8);
      ArrayResize(post, ArraySize(post) - 1);          // drop the trailing zero
     }
   ResetLastError();
   int code = WebRequest(method, url, headers, 20000, post, out, rh);
   resp = CharArrayToString(out, 0, WHOLE_ARRAY, CP_UTF8);
   if(code == -1)
      PrintFormat("FX Bars Pusher: WebRequest failed, error %d (4014 = add https://api.github.com in Tools > Options > Expert Advisors)", GetLastError());
   return code;
  }

//+------------------------------------------------------------------+
//| sha of the file on the data branch, "" when it does not exist    |
//+------------------------------------------------------------------+
string GetSha(const string path)
  {
   string resp = "";
   int code = Http("GET", ApiUrl(path) + "?ref=" + DataBranch, "", resp);
   if(code != 200)
      return "";
   int p = StringFind(resp, "\"sha\":\"");
   if(p < 0)
      return "";
   p += 7;
   int q = StringFind(resp, "\"", p);
   if(q < 0)
      return "";
   return StringSubstr(resp, p, q - p);
  }

bool PutFile(const string path, const string content, const string msg)
  {
   uchar src[];
   uchar key[];
   uchar dst[];
   StringToCharArray(content, src, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(src, ArraySize(src) - 1);
   if(CryptEncode(CRYPT_BASE64, src, key, dst) <= 0)
     {
      Print("FX Bars Pusher: base64 encode failed");
      return false;
     }
   string b64 = CharArrayToString(dst, 0, WHOLE_ARRAY);
   string sha = GetSha(path);
   string body = "{\"message\":\"" + msg + "\",\"content\":\"" + b64 + "\",\"branch\":\"" + DataBranch + "\"";
   if(sha != "")
      body += ",\"sha\":\"" + sha + "\"";
   body += "}";
   string resp = "";
   int code = Http("PUT", ApiUrl(path), body, resp);
   if(code == 200 || code == 201)
      return true;
   PrintFormat("FX Bars Pusher: PUT %s failed, HTTP %d : %s", path, code, StringSubstr(resp, 0, 200));
   return false;
  }

//+------------------------------------------------------------------+
//| JSON of all CLOSED M5 bars of one UTC day                        |
//| bar = [time_utc_epoch, open, high, low, close, tick_volume, spread_points]
//+------------------------------------------------------------------+
bool BuildDayJson(datetime dayUtc, string &json, int &count)
  {
   datetime lastClosed = iTime(g_sym, PERIOD_M5, 1);       // open time of the last closed bar
   if(lastClosed == 0)
      return false;
   datetime fromS = (datetime)((long)dayUtc + g_offset);
   datetime toS   = (datetime)((long)dayUtc + 86400 + g_offset - 1);
   if(toS > lastClosed)
      toS = lastClosed;                                    // never include the forming bar
   if(toS < fromS)
      return false;
   MqlRates r[];
   int n = CopyRates(g_sym, PERIOD_M5, fromS, toS, r);
   if(n <= 0)
      return false;
   int digits = (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS);
   json = "{\"symbol\":\"" + FileSymbol + "\",\"broker_symbol\":\"" + g_sym + "\",\"tf\":\"M5\"," +
          "\"date\":\"" + DateStr(dayUtc) + "\",\"digits\":" + IntegerToString(digits) + "," +
          "\"server_utc_offset_sec\":" + IntegerToString(g_offset) + "," +
          "\"updated_utc\":\"" + IsoNow() + "\",\"bars\":[";
   for(int i = 0; i < n; i++)
     {
      if(i > 0)
         json += ",";
      json += "[" + IntegerToString((long)r[i].time - g_offset) + "," +
              DoubleToString(r[i].open, digits) + "," +
              DoubleToString(r[i].high, digits) + "," +
              DoubleToString(r[i].low, digits) + "," +
              DoubleToString(r[i].close, digits) + "," +
              IntegerToString((long)r[i].tick_volume) + "," +
              IntegerToString((long)r[i].spread) + "]";
     }
   json += "]}";
   count = n;
   return true;
  }

bool PushDay(datetime dayUtc)
  {
   string json = "";
   int n = 0;
   if(!BuildDayJson(dayUtc, json, n))
     {
      PrintFormat("FX Bars Pusher: no bars for %s (weekend, or history not loaded yet)", DateStr(dayUtc));
      return false;
     }
   string msg = "bars " + FileSymbol + " M5 " + DateStr(dayUtc) + " n=" + IntegerToString(n);
   bool ok = PutFile(FilePath(dayUtc), json, msg);
   if(ok)
     {
      g_pushes++;
      g_lastMsg = "pushed " + DateStr(dayUtc) + " (" + IntegerToString(n) + " bars)";
      PrintFormat("FX Bars Pusher: %s", g_lastMsg);
     }
   else
     {
      g_fails++;
      g_lastMsg = "FAILED " + DateStr(dayUtc);
     }
   return ok;
  }

void ShowStatus()
  {
   Comment("FX Bars Pusher v1.00\n",
           "Symbol: ", g_sym, " -> ", FileSymbol, "  (M5)\n",
           "Repo: ", GitHubRepo, "  branch: ", DataBranch, "\n",
           "Server UTC offset: ", IntegerToString(g_offset / 3600), " h\n",
           g_backDone ? "Backfill: done\n" : "Backfill: running (" + IntegerToString(g_backIdx) + " days left)\n",
           "Pushes: ", IntegerToString(g_pushes), "   Fails: ", IntegerToString(g_fails), "\n",
           "Last: ", g_lastMsg);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringLen(GitHubToken) < 10)
     {
      Alert("FX Bars Pusher: type your GitHub token in the EA inputs.");
      return INIT_PARAMETERS_INCORRECT;
     }
   g_sym = BrokerSymbol;
   if(!SymbolSelect(g_sym, true))
     {
      Alert("FX Bars Pusher: symbol not found: ", g_sym);
      return INIT_FAILED;
     }
   g_offset  = CalcOffset();
   g_backIdx = HistoryDays;
   g_backDone = false;
   EventSetTimer(3);
   ShowStatus();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Comment("");
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   g_offset = CalcOffset();
   datetime todayUtc = DayStartUtc(TimeGMT());

   if(!g_backDone)
     {
      if(g_backIdx >= 2)
        {
         // older days: only fill the ones that are missing on GitHub
         datetime d = (datetime)((long)todayUtc - (long)g_backIdx * 86400);
         if(GetSha(FilePath(d)) == "")
           {
            if(PushDay(d))
               Sleep(1500);                              // stay far below GitHub's write limits
           }
         g_backIdx--;
        }
      else if(g_backIdx == 1)
        {
         PushDay((datetime)((long)todayUtc - 86400));    // yesterday, in full
         g_backIdx = 0;
        }
      else
        {
         PushDay(todayUtc);                              // today, in full
         g_lastBar    = iTime(g_sym, PERIOD_M5, 1);
         g_lastDayUtc = todayUtc;
         g_backDone   = true;
         EventKillTimer();
         EventSetTimer(MathMax(5, CheckEverySec));
        }
      ShowStatus();
      return;
     }

   if(TimeLocal() < g_nextTry)
      return;
   datetime t1 = iTime(g_sym, PERIOD_M5, 1);             // last closed bar
   if(t1 == 0 || t1 == g_lastBar)
      return;
   datetime barDay = DayStartUtc((datetime)((long)t1 - g_offset));
   if(barDay > g_lastDayUtc)
      PushDay(g_lastDayUtc);                             // close out the previous day in full
   if(PushDay(barDay))
     {
      g_lastBar    = t1;
      g_lastDayUtc = barDay;
     }
   else
      g_nextTry = TimeLocal() + 60;                      // wait a minute before trying again
   ShowStatus();
  }

void OnTick() { }
//+------------------------------------------------------------------+
