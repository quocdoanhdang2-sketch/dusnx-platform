using System.Collections.Concurrent;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Channels;
using Microsoft.AspNetCore.SignalR;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddProblemDetails();
builder.Services.AddSignalR();
builder.Services.AddCors(options => options.AddDefaultPolicy(policy =>
    policy.SetIsOriginAllowed(_ => true)
        .AllowAnyHeader()
        .AllowAnyMethod()
        .AllowCredentials()));

builder.Services.AddHttpClient("ai", client =>
{
    var baseUrl = Environment.GetEnvironmentVariable("AI_API_URL") ?? "http://localhost:8000";
    client.BaseAddress = new Uri(baseUrl);
    client.Timeout = TimeSpan.FromSeconds(60);
});

builder.Services.AddSingleton<LocalStateStore>();
builder.Services.AddSingleton<JobStore>();
builder.Services.AddSingleton<AiOrchestrator>();
builder.Services.AddSingleton(Channel.CreateUnbounded<PresentationJobRequest>());
builder.Services.AddSingleton(Channel.CreateUnbounded<QueuedPlatformEvent>());
builder.Services.AddHostedService<PresentationJobWorker>();
builder.Services.AddHostedService<PlatformEventWorker>();

var app = builder.Build();

app.UseExceptionHandler();
app.UseStatusCodePages();
app.UseCors();

app.MapGet("/health", () => Results.Ok(new
{
    status = "ok",
    service = "dusnx-gateway",
    phase = "phase-1",
    utc = DateTimeOffset.UtcNow
}));

app.MapPost("/api/v1/events", async (
    EventRequest request,
    AiOrchestrator orchestrator,
    CancellationToken cancellationToken) =>
{
    var validation = RequestValidator.Validate(request);
    if (validation is not null)
        return Results.ValidationProblem(validation);

    try
    {
        var result = await orchestrator.ProcessAsync(request, cancellationToken);
        return Results.Json(result);
    }
    catch (HttpRequestException ex)
    {
        return Results.Problem(
            title: "AI service unavailable",
            detail: ex.Message,
            statusCode: StatusCodes.Status503ServiceUnavailable);
    }
});

// Development-only lookup. Replace with JWT-based /users/me/state in Phase 2.
app.MapGet("/api/v1/state/{platform}/{platformUserId}", async (
    string platform,
    string platformUserId,
    string? linkedUserId,
    LocalStateStore store,
    CancellationToken cancellationToken) =>
{
    var globalUserId = IdentityResolver.Resolve(platform, platformUserId, linkedUserId);
    var state = await store.GetAsync(globalUserId, cancellationToken);
    return state is null
        ? Results.NotFound(new { message = "No state exists for this user yet.", global_user_id = globalUserId })
        : Results.Ok(new
        {
            global_user_id = globalUserId,
            updated_at = state.UpdatedAt,
            state_snapshot = state.StateSnapshot
        });
});

// Development-only history lookup. It is intentionally restricted to loopback
// unless an operator explicitly opts in; production identity must come from auth.
app.MapGet("/api/v1/history/{platform}/{platformUserId}", async (
    HttpContext context,
    string platform,
    string platformUserId,
    string? linkedUserId,
    int? limit,
    string? before,
    LocalStateStore store,
    CancellationToken cancellationToken) =>
{
    if (!HistoryAccess.IsAllowed(context.Connection.RemoteIpAddress, context.Request.Headers.Origin))
        return Results.NotFound();

    var validation = RequestValidator.ValidateIdentity(platform, platformUserId);
    if (validation is not null)
        return Results.ValidationProblem(validation);

    var pageSize = Math.Clamp(limit ?? 25, 1, 100);
    if (!HistoryCursor.TryParse(before, out var beforeSequence))
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["before"] = ["before must be a positive timeline cursor returned by this endpoint."]
        });

    var globalUserId = IdentityResolver.Resolve(platform, platformUserId, linkedUserId);
    var page = await store.ReadHistoryAsync(globalUserId, pageSize, beforeSequence, cancellationToken);
    return Results.Ok(new
    {
        items = page.Items,
        next_cursor = page.NextCursor,
        has_more = page.HasMore
    });
});

app.MapPost("/api/v1/presentations/generations", async (
    PresentationGenerationRequest request,
    Channel<PresentationJobRequest> channel,
    JobStore jobs,
    CancellationToken cancellationToken) =>
{
    if (string.IsNullOrWhiteSpace(request.PlatformUserId) || string.IsNullOrWhiteSpace(request.Prompt))
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["request"] = ["platformUserId and prompt are required."]
        });

    if (request.SlideCount is < 1 or > 20)
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["slideCount"] = ["slideCount must be between 1 and 20."]
        });

    var jobId = Guid.NewGuid().ToString("N");
    var job = new PresentationJobRequest(
        jobId,
        request.PlatformUserId.Trim(),
        request.Prompt.Trim(),
        request.SlideCount,
        request.LinkedUserId);

    var view = jobs.Create(jobId, "presentation");
    await channel.Writer.WriteAsync(job, cancellationToken);
    return Results.Accepted($"/api/v1/jobs/{jobId}", view);
});

app.MapGet("/api/v1/jobs/{jobId}", (string jobId, JobStore jobs) =>
    jobs.TryGet(jobId, out var job)
        ? Results.Ok(job)
        : Results.NotFound(new { message = "Job not found.", job_id = jobId }));

// Phase 1 normalized webhook. Configure ZALO_WEBHOOK_SECRET before exposing a tunnel.
app.MapPost("/webhooks/zalo", async (
    HttpRequest httpRequest,
    ZaloWebhookRequest request,
    Channel<QueuedPlatformEvent> channel,
    LocalStateStore store,
    CancellationToken cancellationToken) =>
{
    var configuredSecret = Environment.GetEnvironmentVariable("ZALO_WEBHOOK_SECRET");
    if (!string.IsNullOrWhiteSpace(configuredSecret))
    {
        var suppliedSecret = httpRequest.Headers["X-DUSNX-Webhook-Secret"].ToString();
        if (!CryptographicOperations.FixedTimeEquals(
                Encoding.UTF8.GetBytes(configuredSecret),
                Encoding.UTF8.GetBytes(suppliedSecret)))
            return Results.Unauthorized();
    }

    var eventId = string.IsNullOrWhiteSpace(request.EventId)
        ? Guid.NewGuid().ToString("N")
        : request.EventId.Trim();

    if (!store.TryMarkEvent(eventId))
        return Results.Ok(new { accepted = true, duplicate = true, event_id = eventId });

    var normalized = new EventRequest(
        "zalo",
        request.UserId,
        request.Message,
        "message",
        request.FeedbackValue,
        request.LinkedUserId);

    await channel.Writer.WriteAsync(new QueuedPlatformEvent(eventId, normalized), cancellationToken);
    return Results.Ok(new { accepted = true, duplicate = false, event_id = eventId });
});

app.MapHub<JobHub>("/hubs/jobs");
app.Run();

public sealed record EventRequest(
    string Platform,
    string PlatformUserId,
    string Content,
    string? EventType,
    double? FeedbackValue,
    string? LinkedUserId);

public sealed record PresentationGenerationRequest(
    string PlatformUserId,
    string Prompt,
    int SlideCount = 5,
    string? LinkedUserId = null);

public sealed record ZaloWebhookRequest(
    string? EventId,
    string UserId,
    string Message,
    double? FeedbackValue = null,
    string? LinkedUserId = null);

public sealed record PresentationJobRequest(
    string JobId,
    string PlatformUserId,
    string Prompt,
    int SlideCount,
    string? LinkedUserId);

public sealed record QueuedPlatformEvent(string EventId, EventRequest Event);
public sealed record StoredState(JsonElement StateSnapshot, DateTimeOffset UpdatedAt);

public sealed record TimelineItem(
    long Cursor,
    [property: JsonPropertyName("event_id")]
    string? EventId,
    [property: JsonPropertyName("event_time_utc")]
    DateTimeOffset? EventTimeUtc,
    string? Platform,
    [property: JsonPropertyName("event_type")]
    string? EventType,
    string? Content,
    [property: JsonPropertyName("known_feedback_value")]
    double? KnownFeedbackValue,
    string? Intent,
    [property: JsonPropertyName("selected_agent")]
    string? SelectedAgent,
    [property: JsonPropertyName("next_action")]
    string? NextAction,
    double? Confidence,
    [property: JsonPropertyName("routing_source")]
    string? RoutingSource,
    [property: JsonPropertyName("runtime_mode")]
    string? RuntimeMode,
    [property: JsonPropertyName("model_version")]
    string? ModelVersion,
    [property: JsonPropertyName("state_version")]
    long? StateVersion,
    [property: JsonPropertyName("state_reset")]
    bool? StateReset,
    [property: JsonPropertyName("reset_reason")]
    string? ResetReason);

public sealed record TimelinePage(IReadOnlyList<TimelineItem> Items, string? NextCursor, bool HasMore);

public sealed record JobView(
    string JobId,
    string Type,
    string Status,
    int Progress,
    string CurrentStep,
    JsonElement? Result,
    string? Error,
    DateTimeOffset UpdatedAt);

public static class RequestValidator
{
    private static readonly HashSet<string> SupportedPlatforms =
        new(StringComparer.OrdinalIgnoreCase) { "web", "zalo", "powerpoint" };

    public static Dictionary<string, string[]>? Validate(EventRequest request)
    {
        var errors = new Dictionary<string, string[]>();
        if (!SupportedPlatforms.Contains(request.Platform?.Trim() ?? string.Empty))
            errors["platform"] = ["platform must be web, zalo or powerpoint."];
        if (string.IsNullOrWhiteSpace(request.PlatformUserId))
            errors["platformUserId"] = ["platformUserId is required."];
        if (string.IsNullOrWhiteSpace(request.Content))
            errors["content"] = ["content is required."];
        else if (request.Content.Length > 10_000)
            errors["content"] = ["content must not exceed 10,000 characters."];
        return errors.Count == 0 ? null : errors;
    }

    public static Dictionary<string, string[]>? ValidateIdentity(string platform, string platformUserId)
    {
        var errors = new Dictionary<string, string[]>();
        if (!SupportedPlatforms.Contains(platform?.Trim() ?? string.Empty))
            errors["platform"] = ["platform must be web, zalo or powerpoint."];
        if (string.IsNullOrWhiteSpace(platformUserId))
            errors["platformUserId"] = ["platformUserId is required."];
        return errors.Count == 0 ? null : errors;
    }
}

public static class HistoryAccess
{
    public static bool IsAllowed(IPAddress? remoteAddress, string? origin = null)
    {
        if (string.Equals(
                Environment.GetEnvironmentVariable("DUSNX_ALLOW_REMOTE_DEV_HISTORY"),
                "true",
                StringComparison.OrdinalIgnoreCase))
            return true;
        var localAddress = remoteAddress is not null
            && (IPAddress.IsLoopback(remoteAddress)
                || (remoteAddress.IsIPv4MappedToIPv6 && IPAddress.IsLoopback(remoteAddress.MapToIPv4())));
        if (!localAddress)
            return false;
        if (string.IsNullOrWhiteSpace(origin))
            return true;
        return Uri.TryCreate(origin, UriKind.Absolute, out var uri)
            && (string.Equals(uri.Host, "localhost", StringComparison.OrdinalIgnoreCase)
                || IPAddress.TryParse(uri.Host, out var originAddress) && IPAddress.IsLoopback(originAddress));
    }
}

public static class HistoryCursor
{
    public static bool TryParse(string? value, out long? sequence)
    {
        sequence = null;
        if (string.IsNullOrWhiteSpace(value))
            return true;
        if (!long.TryParse(value, out var parsed) || parsed < 1)
            return false;
        sequence = parsed;
        return true;
    }
}

public static class IdentityResolver
{
    public static string Resolve(string platform, string platformUserId, string? linkedUserId)
    {
        var identity = !string.IsNullOrWhiteSpace(linkedUserId)
            ? $"linked:{linkedUserId.Trim()}"
            : $"{platform.Trim().ToLowerInvariant()}:{platformUserId.Trim()}";
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(identity));
        return new Guid(bytes[..16]).ToString();
    }
}

public sealed class AiOrchestrator
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly LocalStateStore _store;
    private readonly ConcurrentDictionary<string, SemaphoreSlim> _userGates = new();

    public AiOrchestrator(IHttpClientFactory httpClientFactory, LocalStateStore store)
    {
        _httpClientFactory = httpClientFactory;
        _store = store;
    }

    public async Task<JsonElement> ProcessAsync(
        EventRequest request,
        CancellationToken cancellationToken,
        string? eventId = null)
    {
        var platform = request.Platform.Trim().ToLowerInvariant();
        var globalUserId = IdentityResolver.Resolve(platform, request.PlatformUserId, request.LinkedUserId);
        var userGate = _userGates.GetOrAdd(globalUserId, _ => new SemaphoreSlim(1, 1));
        await userGate.WaitAsync(cancellationToken);
        try
        {
            var previous = await _store.GetAsync(globalUserId, cancellationToken);
            var now = DateTimeOffset.UtcNow;
            var gapHours = previous is null ? 0.0 : Math.Max(0, (now - previous.UpdatedAt).TotalHours);

            var payload = new
            {
                global_user_id = globalUserId,
                platform,
                content = request.Content.Trim(),
                event_type = string.IsNullOrWhiteSpace(request.EventType) ? "message" : request.EventType.Trim(),
                time_gap_hours = gapHours,
                // This value is known before the current event. It is not a rating
                // of the response that this request is about to produce.
                feedback_value = Math.Clamp(request.FeedbackValue ?? 0.0, -1.0, 1.0),
                previous_state = previous?.StateSnapshot
            };

            var client = _httpClientFactory.CreateClient("ai");
            using var response = await client.PostAsJsonAsync("/v1/process", payload, cancellationToken);
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            if (!response.IsSuccessStatusCode)
                throw new HttpRequestException($"AI API returned {(int)response.StatusCode}: {body}");

            using var document = JsonDocument.Parse(body);
            var root = document.RootElement.Clone();
            if (root.TryGetProperty("state_snapshot", out var snapshot))
            {
                if (previous is not null
                    && root.TryGetProperty("state_reset", out var stateReset)
                    && stateReset.ValueKind == JsonValueKind.True)
                    await _store.ArchiveAsync(globalUserId, previous, now, cancellationToken);
                await _store.SaveAsync(globalUserId, snapshot.Clone(), now, cancellationToken);
            }

            await _store.AppendEventAsync(new
            {
                event_id = eventId ?? Guid.NewGuid().ToString("N"),
                global_user_id = globalUserId,
                platform,
                event_type = payload.event_type,
                content = payload.content,
                known_feedback_value = payload.feedback_value,
                event_time_utc = now,
                result = root
            }, cancellationToken);

            return root;
        }
        finally
        {
            userGate.Release();
        }
    }
}

public sealed class LocalStateStore
{
    private readonly ConcurrentDictionary<string, StoredState> _states = new();
    private readonly ConcurrentDictionary<string, byte> _seenEventIds = new();
    private readonly SemaphoreSlim _fileGate = new(1, 1);
    private readonly string _stateDirectory;
    private readonly string _archiveDirectory;
    private readonly string _eventsPath;

    public LocalStateStore(IWebHostEnvironment environment)
        : this(Environment.GetEnvironmentVariable("DUSNX_DATA_DIR")
            ?? Path.Combine(environment.ContentRootPath, "data"))
    {
    }

    public LocalStateStore(string dataDirectory)
    {
        _stateDirectory = Path.Combine(dataDirectory, "state");
        _archiveDirectory = Path.Combine(_stateDirectory, "archive");
        _eventsPath = Path.Combine(dataDirectory, "events.jsonl");
        Directory.CreateDirectory(_stateDirectory);
        Directory.CreateDirectory(_archiveDirectory);
    }

    public bool TryMarkEvent(string eventId) => _seenEventIds.TryAdd(eventId, 0);

    public async Task<StoredState?> GetAsync(string globalUserId, CancellationToken cancellationToken)
    {
        if (_states.TryGetValue(globalUserId, out var cached))
            return cached;

        var path = StatePath(globalUserId);
        if (!File.Exists(path))
            return null;

        var json = await File.ReadAllTextAsync(path, cancellationToken);
        var loaded = JsonSerializer.Deserialize<StoredState>(json);
        if (loaded is not null)
            _states[globalUserId] = loaded;
        return loaded;
    }

    public async Task SaveAsync(
        string globalUserId,
        JsonElement snapshot,
        DateTimeOffset updatedAt,
        CancellationToken cancellationToken)
    {
        var state = new StoredState(snapshot.Clone(), updatedAt);
        _states[globalUserId] = state;
        var json = JsonSerializer.Serialize(state, new JsonSerializerOptions { WriteIndented = true });
        await File.WriteAllTextAsync(StatePath(globalUserId), json, cancellationToken);
    }

    public async Task ArchiveAsync(
        string globalUserId,
        StoredState state,
        DateTimeOffset archivedAt,
        CancellationToken cancellationToken)
    {
        var archive = new
        {
            archived_at = archivedAt,
            reason = "state_reset_by_ai_api",
            previous_state = state
        };
        var fileName = $"{globalUserId}.{archivedAt.UtcDateTime.Ticks}.json";
        var json = JsonSerializer.Serialize(archive, new JsonSerializerOptions { WriteIndented = true });
        await File.WriteAllTextAsync(Path.Combine(_archiveDirectory, fileName), json, cancellationToken);
    }

    public async Task AppendEventAsync(object eventRecord, CancellationToken cancellationToken)
    {
        var line = JsonSerializer.Serialize(eventRecord) + Environment.NewLine;
        await _fileGate.WaitAsync(cancellationToken);
        try
        {
            await File.AppendAllTextAsync(_eventsPath, line, cancellationToken);
        }
        finally
        {
            _fileGate.Release();
        }
    }

    public async Task<TimelinePage> ReadHistoryAsync(
        string globalUserId,
        int limit,
        long? beforeSequence,
        CancellationToken cancellationToken)
    {
        limit = Math.Clamp(limit, 1, 100);
        if (!File.Exists(_eventsPath))
            return new TimelinePage([], null, false);

        var recent = new Queue<TimelineItem>(limit + 1);
        long lineNumber = 0;
        await using var stream = new FileStream(
            _eventsPath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete,
            bufferSize: 4096,
            useAsync: true);
        using var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);

        while (await reader.ReadLineAsync(cancellationToken) is { } line)
        {
            lineNumber++;
            if (beforeSequence is not null && lineNumber >= beforeSequence.Value)
                continue;
            if (string.IsNullOrWhiteSpace(line))
                continue;

            try
            {
                using var document = JsonDocument.Parse(line);
                var root = document.RootElement;
                if (root.ValueKind != JsonValueKind.Object
                    || GetString(root, "global_user_id") != globalUserId)
                    continue;

                recent.Enqueue(ToTimelineItem(root, lineNumber));
                if (recent.Count > limit + 1)
                    recent.Dequeue();
            }
            catch (JsonException)
            {
                // JSONL is append-only. One damaged legacy line must not hide
                // the valid events before or after it.
            }
        }

        var newestFirst = recent.Reverse().ToList();
        var hasMore = newestFirst.Count > limit;
        var items = newestFirst.Take(limit).ToList();
        var nextCursor = hasMore ? items[^1].Cursor.ToString() : null;
        return new TimelinePage(items, nextCursor, hasMore);
    }

    private static TimelineItem ToTimelineItem(JsonElement root, long cursor)
    {
        var result = GetObject(root, "result");
        var state = result is { } resultValue ? GetObject(resultValue, "state_snapshot") : null;
        return new TimelineItem(
            cursor,
            GetScalarText(root, "event_id"),
            GetDateTimeOffset(root, "event_time_utc"),
            GetString(root, "platform"),
            GetString(root, "event_type"),
            GetString(root, "content"),
            GetDouble(root, "known_feedback_value"),
            result is { } r1 ? GetString(r1, "intent") : null,
            result is { } r2 ? GetString(r2, "selected_agent") : null,
            result is { } r3 ? GetString(r3, "next_action") : null,
            result is { } r4 ? GetDouble(r4, "confidence") : null,
            result is { } r5 ? GetString(r5, "routing_source") : null,
            result is { } r6 ? GetString(r6, "runtime_mode") : null,
            state is { } s1 ? GetString(s1, "model_version") : null,
            state is { } s2 ? GetLong(s2, "state_version") : null,
            result is { } r7 ? GetBool(r7, "state_reset") : null,
            result is { } r8 ? GetString(r8, "reset_reason") : null);
    }

    private static JsonElement? GetObject(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Object ? value : null;

    private static string? GetString(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    private static string? GetScalarText(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind is JsonValueKind.String or JsonValueKind.Number
            ? value.ToString()
            : null;

    private static double? GetDouble(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.TryGetDouble(out var parsed) ? parsed : null;

    private static long? GetLong(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.TryGetInt64(out var parsed) ? parsed : null;

    private static bool? GetBool(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind is JsonValueKind.True or JsonValueKind.False
            ? value.GetBoolean()
            : null;

    private static DateTimeOffset? GetDateTimeOffset(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.String
        && value.TryGetDateTimeOffset(out var parsed)
            ? parsed
            : null;

    private string StatePath(string globalUserId) => Path.Combine(_stateDirectory, $"{globalUserId}.json");
}

public sealed class JobStore
{
    private readonly ConcurrentDictionary<string, JobView> _jobs = new();

    public JobView Create(string jobId, string type)
    {
        var job = new JobView(jobId, type, "queued", 0, "queued", null, null, DateTimeOffset.UtcNow);
        _jobs[jobId] = job;
        return job;
    }

    public JobView Update(
        string jobId,
        string status,
        int progress,
        string currentStep,
        JsonElement? result = null,
        string? error = null)
    {
        if (!_jobs.TryGetValue(jobId, out var current))
            throw new KeyNotFoundException($"Unknown job {jobId}");

        var updated = current with
        {
            Status = status,
            Progress = progress,
            CurrentStep = currentStep,
            Result = result?.Clone(),
            Error = error,
            UpdatedAt = DateTimeOffset.UtcNow
        };
        _jobs[jobId] = updated;
        return updated;
    }

    public bool TryGet(string jobId, out JobView job) => _jobs.TryGetValue(jobId, out job!);
}

public sealed class JobHub : Hub
{
    public Task Subscribe(string jobId) => Groups.AddToGroupAsync(Context.ConnectionId, jobId);
    public Task Unsubscribe(string jobId) => Groups.RemoveFromGroupAsync(Context.ConnectionId, jobId);
}

public sealed class PresentationJobWorker : BackgroundService
{
    private readonly Channel<PresentationJobRequest> _channel;
    private readonly JobStore _jobs;
    private readonly AiOrchestrator _orchestrator;
    private readonly IHubContext<JobHub> _hub;

    public PresentationJobWorker(
        Channel<PresentationJobRequest> channel,
        JobStore jobs,
        AiOrchestrator orchestrator,
        IHubContext<JobHub> hub)
    {
        _channel = channel;
        _jobs = jobs;
        _orchestrator = orchestrator;
        _hub = hub;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await foreach (var request in _channel.Reader.ReadAllAsync(stoppingToken))
        {
            try
            {
                var processing = _jobs.Update(request.JobId, "processing", 20, "updating_user_state");
                await _hub.Clients.Group(request.JobId).SendAsync("JobProgressUpdated", processing, stoppingToken);

                var eventRequest = new EventRequest(
                    "powerpoint",
                    request.PlatformUserId,
                    $"Create {request.SlideCount} slides. {request.Prompt}",
                    "presentation.generate_requested",
                    0,
                    request.LinkedUserId);

                var result = await _orchestrator.ProcessAsync(eventRequest, stoppingToken);
                var completed = _jobs.Update(request.JobId, "completed", 100, "completed", result);
                await _hub.Clients.Group(request.JobId).SendAsync("JobCompleted", completed, stoppingToken);
            }
            catch (Exception ex)
            {
                var failed = _jobs.Update(request.JobId, "failed", 100, "failed", error: ex.Message);
                await _hub.Clients.Group(request.JobId).SendAsync("JobFailed", failed, stoppingToken);
            }
        }
    }
}

public sealed class PlatformEventWorker : BackgroundService
{
    private readonly Channel<QueuedPlatformEvent> _channel;
    private readonly AiOrchestrator _orchestrator;
    private readonly LocalStateStore _store;
    private readonly ILogger<PlatformEventWorker> _logger;

    public PlatformEventWorker(
        Channel<QueuedPlatformEvent> channel,
        AiOrchestrator orchestrator,
        LocalStateStore store,
        ILogger<PlatformEventWorker> logger)
    {
        _channel = channel;
        _orchestrator = orchestrator;
        _store = store;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await foreach (var queued in _channel.Reader.ReadAllAsync(stoppingToken))
        {
            try
            {
                await _orchestrator.ProcessAsync(queued.Event, stoppingToken, queued.EventId);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to process platform event {EventId}", queued.EventId);
            }
        }
    }
}
