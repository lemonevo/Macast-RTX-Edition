-- Macast RTX Edition: adaptive NVIDIA RTX Video filter management.
--
-- RTX VSR only runs when the video is actually being enlarged and the source
-- is at most 1440p. RTX Video HDR is safe to keep enabled because the NVIDIA
-- processor ignores content that is already HDR.

local mp = require("mp")
local options = require("mp.options")

local settings = {
    vsr = true,
    hdr = false,
    max_input_height = 1440,
    max_scale = 4.0,
    min_scale = 1.05,
}

options.read_options(settings, "macast_rtx")

local filter_label = "@macast-rtx"
local active_signature = nil

local function remove_filter()
    if active_signature == nil then
        return
    end
    pcall(mp.commandv, "vf", "remove", filter_label)
    active_signature = nil
end

local function target_scale()
    local width = mp.get_property_number("video-params/w")
    local height = mp.get_property_number("video-params/h")
    local output_width = mp.get_property_number("osd-width")
        or mp.get_property_number("display-width")
    local output_height = mp.get_property_number("osd-height")
        or mp.get_property_number("display-height")

    if not width or not height or not output_width or not output_height then
        return nil, height
    end

    local scale = math.min(output_width / width, output_height / height)
    scale = math.min(scale, settings.max_scale)
    return scale, height
end

local function update_filter()
    local args = {}
    local scale, source_height = target_scale()

    if settings.vsr
        and scale
        and source_height
        and source_height <= settings.max_input_height
        and scale >= settings.min_scale then
        table.insert(args, "scale=" .. string.format("%.3f", scale))
        table.insert(args, "scaling-mode=nvidia")
    end

    if settings.hdr then
        table.insert(args, "nvidia-true-hdr=yes")
    end

    if #args == 0 then
        remove_filter()
        return
    end

    local signature = table.concat(args, ":")
    if signature == active_signature then
        return
    end

    remove_filter()
    local filter = filter_label .. ":d3d11vpp=" .. signature
    local ok, error_message = pcall(mp.commandv, "vf", "add", filter)
    if ok then
        active_signature = signature
        mp.msg.info("RTX Video filter enabled: " .. signature)
    else
        mp.msg.error("Unable to enable RTX Video filter: " .. tostring(error_message))
    end
end

mp.register_event("file-loaded", update_filter)
mp.register_event("video-reconfig", update_filter)
mp.observe_property("osd-width", "native", update_filter)
mp.observe_property("osd-height", "native", update_filter)
mp.observe_property("video-params/w", "native", update_filter)
mp.observe_property("video-params/h", "native", update_filter)
