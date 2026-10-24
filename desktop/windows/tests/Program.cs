using Microsoft.Web.WebView2.Core;
using Shuran.Desktop;
using System.Text.Json;

var assertions = 0;
void Check(bool value, string message)
{
    if (!value) throw new Exception(message);
    assertions++;
}

foreach (var code in new[] { 408, 502, 503, 504 })
{
    var policy = new NavigationRecovery();
    policy.ObserveNavigation(1);
    var failure = NavigationFailure.From(code, CoreWebView2WebErrorStatus.Unknown);
    Check(policy.NextDelay(failure) == 2, $"{code}: first retry");
    Check(policy.NextDelay(failure) == 5, $"{code}: second retry");
    Check(policy.NextDelay(failure) == 10, $"{code}: third retry");
    Check(policy.NextDelay(failure) is null && policy.RetryCount == 3, $"{code}: bounded retries");
    policy.Reset();
    policy.ObserveNavigation(2);
    Check(policy.NextDelay(failure) == 2, $"{code}: manual reconnect resets budget");
    policy.MarkLoaded();
    Check(policy.NextDelay(failure) is null, $"{code}: loaded page must not reload");
}
foreach (var code in new[] { 400, 401, 403, 404, 407, 429, 500 })
    Check(!NavigationFailure.From(code, CoreWebView2WebErrorStatus.Unknown).CanRetry, $"{code}: no blind retry");
foreach (var error in new[] {
    CoreWebView2WebErrorStatus.CertificateCommonNameIsIncorrect,
    CoreWebView2WebErrorStatus.CertificateExpired,
    CoreWebView2WebErrorStatus.CertificateIsInvalid,
    CoreWebView2WebErrorStatus.CertificateRevoked,
    CoreWebView2WebErrorStatus.ClientCertificateContainsErrors,
    CoreWebView2WebErrorStatus.ValidAuthenticationCredentialsRequired,
    CoreWebView2WebErrorStatus.ValidProxyAuthenticationRequired,
    CoreWebView2WebErrorStatus.OperationCanceled })
    Check(!NavigationFailure.From(0, error).CanRetry, $"{error}: no retry or bypass");
foreach (var error in new[] {
    CoreWebView2WebErrorStatus.Timeout, CoreWebView2WebErrorStatus.CannotConnect,
    CoreWebView2WebErrorStatus.ConnectionReset, CoreWebView2WebErrorStatus.Disconnected,
    CoreWebView2WebErrorStatus.HostNameNotResolved, CoreWebView2WebErrorStatus.ServerUnreachable,
    CoreWebView2WebErrorStatus.ConnectionAborted })
    Check(NavigationFailure.From(0, error).CanRetry, $"{error}: retry transient network failures");
Check(NavigationFailure.From(0, CoreWebView2WebErrorStatus.OperationCanceled).IsCanceled, "Ignore stale canceled completions");
var guarded = new NavigationRecovery();
var transient = NavigationFailure.From(502, CoreWebView2WebErrorStatus.Unknown);
guarded.ObserveNavigation(10);
guarded.ObserveNavigation(10); // Redirects keep the original navigation ID.
Check(guarded.NextDelay(transient) == 2, "Allow bootstrap redirects");
guarded.ObserveNavigation(11); // A form submission or another navigation is not our bootstrap GET.
Check(guarded.NextDelay(transient) is null, "Never replay another navigation before bootstrap finishes");
guarded.BeginConnection();
guarded.ObserveNavigation(12);
Check(guarded.NextDelay(transient) == 5, "Next explicit GET keeps the finite retry budget");
var update = JsonSerializer.Deserialize<DesktopUpdater.UpdateInfo>("""
    {"windows_version":"1.6.5","windows_available":true,"windows_download_url":"/download/windows","windows_size_bytes":1234567}
    """);
Check(update is { WindowsVersion: "1.6.5", WindowsAvailable: true }, "Read server's snake_case update fields");
Check(update is { WindowsDownloadUrl: "/download/windows", WindowsSizeBytes: 1234567 }, "Read update download and size");
Console.WriteLine($"Recovery policy: {assertions} assertions passed.");
