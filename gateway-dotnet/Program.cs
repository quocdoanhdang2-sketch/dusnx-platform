using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
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

    public AiOrchestrator(IHttpClientFactory httpClientFactory, LocalStateStore store)
    {
        _httpClientFactory = httpClientFactory;
        _store = store;
    }

    public async Task<JsonElement> ProcessAsync(EventRequest request, CancellationToken cancellationToken)
    {
        var platform = request.Platform.Trim().ToLowerInvariant();
        var globalUserId = IdentityResolver.Resolve(platform, request.PlatformUserId, request.LinkedUserId);
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
            await _store.SaveAsync(globalUserId, snapshot.Clone(), now, cancellationToken);

        await _store.AppendEventAsync(new
        {
            event_id = Guid.NewGuid(),
            global_user_id = globalUserId,
            platform,
            event_type = payload.event_type,
            content = payload.content,
            feedback_value = payload.feedback_value,
            event_time_utc = now,
            result = root
        }, cancellationToken);

        return root;
    }
}

public sealed class LocalStateStore
{
    private readonly ConcurrentDictionary<string, StoredState> _states = new();
    private readonly ConcurrentDictionary<string, byte> _seenEventIds = new();
    private readonly SemaphoreSlim _fileGate = new(1, 1);
    private readonly string _stateDirectory;
    private readonly string _eventsPath;

    public LocalStateStore(IWebHostEnvironment environment)
    {
        var dataDirectory = Environment.GetEnvironmentVariable("DUSNX_DATA_DIR")
            ?? Path.Combine(environment.ContentRootPath, "data");
        _stateDirectory = Path.Combine(dataDirectory, "state");
        _eventsPath = Path.Combine(dataDirectory, "events.jsonl");
        Directory.CreateDirectory(_stateDirectory);
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
                var result = await _orchestrator.ProcessAsync(queued.Event, stoppingToken);
                await _store.AppendEventAsync(new
                {
                    event_id = queued.EventId,
                    source = "zalo_webhook_worker",
                    processed = true,
                    result
                }, stoppingToken);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to process platform event {EventId}", queued.EventId);
            }
        }
    }
}
