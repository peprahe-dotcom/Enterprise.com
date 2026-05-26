#property strict

#include <Trade/Trade.mqh>

input string AccountId = "DEFAULT";
input int PollMs = 250;
input long MagicNumber = 20240001;
input bool AllowLive = false;

CTrade Trade;

string BaseDir()
{
   return "GodTierBot";
}

string SignalFile()
{
   return BaseDir() + "\\signals\\" + AccountId + ".json";
}

string ConfirmFile(string signalId)
{
   return BaseDir() + "\\confirms\\" + signalId + ".json";
}

string ExtractString(string json, string key)
{
   string needle = "\"" + key + "\"";
   int p = StringFind(json, needle);
   if(p < 0) return "";
   p = StringFind(json, ":", p);
   if(p < 0) return "";
   p++;
   while(p < (int)StringLen(json) && (StringGetCharacter(json, p) == ' ')) p++;
   if(p >= (int)StringLen(json)) return "";
   if(StringGetCharacter(json, p) != '"') return "";
   p++;
   int q = StringFind(json, "\"", p);
   if(q < 0) return "";
   return StringSubstr(json, p, q - p);
}

double ExtractDouble(string json, string key, double def)
{
   string needle = "\"" + key + "\"";
   int p = StringFind(json, needle);
   if(p < 0) return def;
   p = StringFind(json, ":", p);
   if(p < 0) return def;
   p++;
   while(p < (int)StringLen(json) && (StringGetCharacter(json, p) == ' ')) p++;
   int q = p;
   while(q < (int)StringLen(json))
   {
      int c = StringGetCharacter(json, q);
      if((c >= '0' && c <= '9') || c == '.' || c == '-' || c == '+')
      {
         q++;
         continue;
      }
      break;
   }
   string num = StringSubstr(json, p, q - p);
   if(num == "") return def;
   return StringToDouble(num);
}

long ExtractLong(string json, string key, long def)
{
   double v = ExtractDouble(json, key, (double)def);
   return (long)v;
}

bool WriteConfirm(string signalId, string status, long ticket, string errorMsg)
{
   string path = ConfirmFile(signalId);
   int h = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_COMMON, '\n');
   if(h == INVALID_HANDLE) return false;

   string msg = "{\"signal_id\":\"" + signalId + "\",\"status\":\"" + status + "\",\"ticket\":" + (string)ticket + ",\"error_msg\":\"" + errorMsg + "\"}";
   FileWriteString(h, msg);
   FileClose(h);
   return true;
}

bool CanTrade()
{
   if(AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) == 0) return false;
   if(MQLInfoInteger(MQL_TRADE_ALLOWED) == 0) return false;
   if(!AllowLive)
   {
      long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
      if(mode != ACCOUNT_TRADE_MODE_DEMO) return false;
   }
   return true;
}

void ProcessSignal(string json)
{
   string signalId = ExtractString(json, "signal_id");
   if(signalId == "") signalId = (string)TimeCurrent();

   string action = ExtractString(json, "action");
   if(action == "")
   {
      WriteConfirm(signalId, "ERROR", 0, "missing_action");
      return;
   }

   if(action == "PING")
   {
      WriteConfirm(signalId, "OK", 0, "");
      return;
   }

   if(!CanTrade())
   {
      WriteConfirm(signalId, "REJECTED", 0, "trade_not_allowed");
      return;
   }

   if(action == "OPEN")
   {
      string symbol = ExtractString(json, "symbol");
      string side = ExtractString(json, "side");
      double lots = ExtractDouble(json, "lots", 0.0);
      double sl = ExtractDouble(json, "sl", 0.0);
      double tp = ExtractDouble(json, "tp", 0.0);
      string comment = ExtractString(json, "comment");

      if(symbol == "" || (side != "BUY" && side != "SELL") || lots <= 0.0)
      {
         WriteConfirm(signalId, "ERROR", 0, "bad_order_fields");
         return;
      }

      if(!SymbolSelect(symbol, true))
      {
         WriteConfirm(signalId, "ERROR", 0, "symbol_select_failed");
         return;
      }

      Trade.SetExpertMagicNumber(MagicNumber);
      Trade.SetDeviationInPoints(20);

      bool ok = false;
      if(side == "BUY")
      {
         ok = Trade.Buy(lots, symbol, 0.0, sl > 0 ? sl : 0.0, tp > 0 ? tp : 0.0, comment);
      }
      else
      {
         ok = Trade.Sell(lots, symbol, 0.0, sl > 0 ? sl : 0.0, tp > 0 ? tp : 0.0, comment);
      }

      if(!ok)
      {
         WriteConfirm(signalId, "ERROR", 0, (string)Trade.ResultRetcode());
         return;
      }

      long ticket = (long)Trade.ResultOrder();
      WriteConfirm(signalId, "FILLED", ticket, "");
      return;
   }

   if(action == "CLOSE")
   {
      long ticket = ExtractLong(json, "ticket", 0);
      if(ticket <= 0)
      {
         WriteConfirm(signalId, "ERROR", 0, "bad_ticket");
         return;
      }
      Trade.SetExpertMagicNumber(MagicNumber);
      bool ok = Trade.PositionClose(ticket);
      if(!ok)
      {
         WriteConfirm(signalId, "ERROR", ticket, (string)Trade.ResultRetcode());
         return;
      }
      WriteConfirm(signalId, "CLOSED", ticket, "");
      return;
   }

   WriteConfirm(signalId, "ERROR", 0, "unknown_action");
}

void OnTimer()
{
   string path = SignalFile();
   int h = FileOpen(path, FILE_READ | FILE_TXT | FILE_COMMON, '\n');
   if(h == INVALID_HANDLE) return;
   string json = FileReadString(h);
   FileClose(h);
   FileDelete(path, FILE_COMMON);
   if(json == "") return;
   ProcessSignal(json);
}

int OnInit()
{
   EventSetMillisecondTimer(PollMs);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}
