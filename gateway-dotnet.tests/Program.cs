using System.Net;
using System.Text.Json;

var failures = new List<string>();
await Run("missing and empty history", TestMissingAndEmptyHistory);
await Run("legacy, malformed and isolated users", TestLegacyMalformedAndIsolation);
await Run("pagination and stable append order", TestPaginationAndOrder);
await Run("concurrent JSONL append", TestConcurrentAppend);
await Run("linked identity across platforms", TestLinkedIdentity);
await Run("history access is local by default", TestHistoryAccess);
await Run("timeline JSON contract uses snake case", TestTimelineJsonContract);

if (failures.Count > 0)
{
    Console.Error.WriteLine(string.Join(Environment.NewLine, failures));
    return 1;
}

Console.WriteLine("Gateway history tests passed (7/7).");
return 0;

async Task Run(string name, Func<Task> test)
{
    try
    {
        await test();
        Console.WriteLine($"PASS: {name}");
    }
    catch (Exception ex)
    {
        failures.Add($"FAIL: {name}: {ex.Message}");
    }
}

static async Task TestMissingAndEmptyHistory()
{
    await WithStore(async (store, directory) =>
    {
        Assert((await store.ReadHistoryAsync("user", 10, null, default)).Items.Count == 0, "missing file must be empty");
        await File.WriteAllTextAsync(Path.Combine(directory, "events.jsonl"), "\r\n");
        Assert((await store.ReadHistoryAsync("user", 10, null, default)).Items.Count == 0, "blank file must be empty");
    });
}

static async Task TestLegacyMalformedAndIsolation()
{
    await WithStore(async (store, directory) =>
    {
        var path = Path.Combine(directory, "events.jsonl");
        await File.WriteAllLinesAsync(path,
        [
            "{\"event_id\":\"old-1\",\"global_user_id\":\"alice\",\"platform\":\"web\",\"content\":\"legacy\"}",
            "{broken json",
            "",
            "{\"event_id\":\"bob-1\",\"global_user_id\":\"bob\",\"platform\":\"zalo\"}",
            "{\"event_id\":\"old-2\",\"global_user_id\":\"alice\",\"platform\":\"powerpoint\",\"result\":{\"intent\":\"chat\"}}"
        ]);

        var page = await store.ReadHistoryAsync("alice", 10, null, default);
        Assert(page.Items.Select(x => x.EventId).SequenceEqual(["old-2", "old-1"]), "must skip malformed lines and isolate alice");
        Assert(page.Items[1].Intent is null, "missing legacy result fields must remain null");
    });
}

static async Task TestPaginationAndOrder()
{
    await WithStore(async (store, _) =>
    {
        for (var i = 1; i <= 5; i++)
            await store.AppendEventAsync(Event($"event-{i}", "alice", "2026-01-01T00:00:00Z"), default);

        var first = await store.ReadHistoryAsync("alice", 2, null, default);
        Assert(first.Items.Select(x => x.EventId).SequenceEqual(["event-5", "event-4"]), "first page must use append order for tied timestamps");
        Assert(first.HasMore && first.NextCursor == "4", "first page cursor must point before oldest returned line");

        var second = await store.ReadHistoryAsync("alice", 2, long.Parse(first.NextCursor!), default);
        Assert(second.Items.Select(x => x.EventId).SequenceEqual(["event-3", "event-2"]), "second page must not duplicate items");
        Assert(second.HasMore, "third page must remain available");
    });
}

static async Task TestConcurrentAppend()
{
    await WithStore(async (store, directory) =>
    {
        await Task.WhenAll(Enumerable.Range(0, 80).Select(i =>
            store.AppendEventAsync(Event($"concurrent-{i}", "alice", "2026-01-01T00:00:00Z"), default)));

        var lines = await File.ReadAllLinesAsync(Path.Combine(directory, "events.jsonl"));
        Assert(lines.Length == 80, "every concurrent append must produce one line");
        foreach (var line in lines)
            using (JsonDocument.Parse(line)) { }
    });
}

static Task TestLinkedIdentity()
{
    var web = IdentityResolver.Resolve("web", "web-user", "shared-test-key");
    var zalo = IdentityResolver.Resolve("zalo", "zalo-user", "shared-test-key");
    var powerpoint = IdentityResolver.Resolve("powerpoint", "ppt-user", "shared-test-key");
    var other = IdentityResolver.Resolve("web", "web-user", "other-test-key");
    Assert(web == zalo && zalo == powerpoint, "same linked key must resolve across platforms");
    Assert(web != other, "different linked keys must remain isolated");
    return Task.CompletedTask;
}

static Task TestHistoryAccess()
{
    var previous = Environment.GetEnvironmentVariable("DUSNX_ALLOW_REMOTE_DEV_HISTORY");
    try
    {
        Environment.SetEnvironmentVariable("DUSNX_ALLOW_REMOTE_DEV_HISTORY", null);
        Assert(HistoryAccess.IsAllowed(IPAddress.Loopback), "loopback must be allowed");
        Assert(HistoryAccess.IsAllowed(IPAddress.Parse("::ffff:127.0.0.1")), "IPv4-mapped loopback from Kestrel must be allowed");
        Assert(!HistoryAccess.IsAllowed(IPAddress.Parse("192.0.2.10")), "remote address must be denied by default");
        Assert(HistoryAccess.IsAllowed(IPAddress.Loopback, "http://localhost:3000"), "local Web demo origin must be allowed");
        Assert(!HistoryAccess.IsAllowed(IPAddress.Loopback, "https://example.test"), "non-local browser origin must be denied");
    }
    finally
    {
        Environment.SetEnvironmentVariable("DUSNX_ALLOW_REMOTE_DEV_HISTORY", previous);
    }
    return Task.CompletedTask;
}

static Task TestTimelineJsonContract()
{
    var item = new TimelineItem(1, "event", null, "web", "message", "content", 0, "chat",
        "conversation", "reply", 0.5, "model", "trained_dusnx", "version", 2, false, null);
    var json = JsonSerializer.Serialize(item, new JsonSerializerOptions(JsonSerializerDefaults.Web));
    using var document = JsonDocument.Parse(json);
    var root = document.RootElement;
    Assert(root.TryGetProperty("state_version", out _), "state_version must be snake case");
    Assert(root.TryGetProperty("routing_source", out _), "routing_source must be snake case");
    Assert(!root.TryGetProperty("stateVersion", out _), "camelCase stateVersion must not leak into API");
    return Task.CompletedTask;
}

static object Event(string eventId, string globalUserId, string timestamp) => new
{
    event_id = eventId,
    global_user_id = globalUserId,
    platform = "web",
    event_type = "message",
    content = eventId,
    known_feedback_value = 0.0,
    event_time_utc = timestamp,
    result = new
    {
        intent = "chat",
        selected_agent = "conversation",
        next_action = "reply",
        confidence = 0.5,
        routing_source = "model",
        runtime_mode = "test",
        state_reset = false,
        reset_reason = (string?)null,
        state_snapshot = new { state_version = 1, model_version = "test-model" }
    }
};

static async Task WithStore(Func<LocalStateStore, string, Task> action)
{
    var directory = Path.Combine(Path.GetTempPath(), $"dusnx-history-tests-{Guid.NewGuid():N}");
    Directory.CreateDirectory(directory);
    try
    {
        await action(new LocalStateStore(directory), directory);
    }
    finally
    {
        Directory.Delete(directory, recursive: true);
    }
}

static void Assert(bool condition, string message)
{
    if (!condition)
        throw new InvalidOperationException(message);
}
