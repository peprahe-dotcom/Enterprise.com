#property strict

#include <Trade/Trade.mqh>

input string BaseUrl = "http://127.0.0.1:8080";
input string AccountId = "ACCOUNT_1";
input string Token = "";
input int PollSeconds = 1;

CTrade trade;
bool g_paused = false;
bool g_first = true;

string EscapeJson(const string s)
{
   string out = s;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   return out;
}

string BuildPollBody()
{
   long ms = (long)(TimeCurrent() * 1000);
   string body = "{";
   body += "\"account_id\":\"" + EscapeJson(AccountId) + "\",";
   if(StringLen(Token) > 0)
      body += "\"token\":\"" + EscapeJson(Token) + "\",";
   body += "\"terminal\":\"MT5\",";
   body += "\"timestamp_ms\":" + (string)ms;
   body += "}";
   return body;
}

bool HasCommand(const string resp, const string cmdType)
{
   string needle = "\"type\":\"" + cmdType + "\"";
   return StringFind(resp, needle) >= 0;
}

void Poll()
{
   string url = BaseUrl + "/mt5/poll";
   string body = BuildPollBody();

   char data[];
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);

   char result[];
   string headers = "Content-Type: application/json\r\n";
   int timeout = 3000;

   ResetLastError();
   int res = WebRequest("POST", url, headers, timeout, data, result, headers);
   if(res == -1)
   {
      int err = GetLastError();
      if(g_first)
      {
         Print("GodTierBridge WebRequest failed. Add URL in MT5: Tools->Options->Expert Advisors->Allow WebRequest: ", BaseUrl);
         g_first = false;
      }
      return;
   }

   string resp = CharArrayToString(result, 0, -1, CP_UTF8);
   if(HasCommand(resp, "pause"))
      g_paused = true;
   if(HasCommand(resp, "resume"))
      g_paused = false;
}

int OnInit()
{
   EventSetTimer(PollSeconds);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   Poll();
}

void OnTick()
{
   if(g_paused)
      return;
}

