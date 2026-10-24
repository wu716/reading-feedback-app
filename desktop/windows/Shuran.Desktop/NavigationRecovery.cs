using Microsoft.Web.WebView2.Core;

namespace Shuran.Desktop;

internal sealed record NavigationFailure(string Title, string Message, bool CanRetry, bool IsCanceled = false)
{
    public static NavigationFailure From(int httpStatus, CoreWebView2WebErrorStatus error)
    {
        if (error is CoreWebView2WebErrorStatus.CertificateCommonNameIsIncorrect
            or CoreWebView2WebErrorStatus.CertificateExpired
            or CoreWebView2WebErrorStatus.ClientCertificateContainsErrors
            or CoreWebView2WebErrorStatus.CertificateRevoked
            or CoreWebView2WebErrorStatus.CertificateIsInvalid)
            return new("连接安全验证未通过", "请检查电脑时间或联系书然支持。不会自动忽略证书错误。", false);
        if (httpStatus is 401 or 403 or 407
            || error is CoreWebView2WebErrorStatus.ValidAuthenticationCredentialsRequired
                or CoreWebView2WebErrorStatus.ValidProxyAuthenticationRequired)
            return new("连接需要验证", "请检查登录或代理的验证要求，处理完成后再重新连接。", false);
        if (error == CoreWebView2WebErrorStatus.OperationCanceled)
            return new("连接已取消", "可以随时重新连接。", false, true);
        if (httpStatus is 502 or 503 or 504 or 408)
            return new("暂时无法连接书然", "服务或网络暂时没有正常响应，正在尝试恢复连接。", true);
        if (httpStatus >= 400)
            return new("暂时无法打开页面", "页面返回了错误，请稍后重新连接；持续发生时可查看诊断并联系支持。", false);
        if (error is CoreWebView2WebErrorStatus.Timeout
            or CoreWebView2WebErrorStatus.ServerUnreachable
            or CoreWebView2WebErrorStatus.ConnectionAborted
            or CoreWebView2WebErrorStatus.ConnectionReset
            or CoreWebView2WebErrorStatus.Disconnected
            or CoreWebView2WebErrorStatus.CannotConnect
            or CoreWebView2WebErrorStatus.HostNameNotResolved)
            return new("连接暂时中断", "请保持网络连接，书然正在尝试重新连接。", true);
        return new("暂时无法打开书然", "请检查网络或代理设置后重新连接。", false);
    }
}

internal sealed class NavigationRecovery
{
    static readonly int[] Delays = [2, 5, 10];
    public const int MaximumRetries = 3;
    public int RetryCount { get; private set; }
    public bool PageLoaded { get; private set; }
    ulong? _bootstrapId;
    bool _awaitingBootstrap = true;
    public bool CanRetryNavigation { get; private set; }

    public void BeginConnection()
    {
        _bootstrapId = null;
        _awaitingBootstrap = true;
        CanRetryNavigation = false;
    }

    public void ObserveNavigation(ulong navigationId)
    {
        if (_awaitingBootstrap)
        {
            _bootstrapId = navigationId;
            _awaitingBootstrap = false;
        }
        CanRetryNavigation = !PageLoaded && _bootstrapId == navigationId;
    }

    public void Reset()
    {
        RetryCount = 0;
        PageLoaded = false;
        BeginConnection();
    }

    public void MarkLoaded() => PageLoaded = true;

    public int? NextDelay(NavigationFailure failure)
    {
        // Retry only bootstrap GET navigation, never reload an already usable page
        // or replay a user's POST, save request, or later in-page operation.
        if (PageLoaded || !CanRetryNavigation || !failure.CanRetry || RetryCount >= Delays.Length) return null;
        return Delays[RetryCount++];
    }
}
