import os, re, asyncio, aiohttp, logging, pytz
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import ListenerTimeout
import config

# --- Setup ---
join = config.join
india_timezone = pytz.timezone('Asia/Kolkata')
CHANNEL_ID = -1002601604234  # Log Channel

async def get_classplus_content(session, headers, batch_token, folder_id=0, level=0):
    results = []
    v_count, p_count, i_count = 0, 0, 0
    
    try:
        url = f'https://api.classplusapp.com/v2/course/preview/content/list/{batch_token}'
        params = {'folderId': folder_id, 'limit': 1000}
        
        async with session.get(url, params=params, headers=headers, timeout=30) as res:
            if res.status == 429:
                await asyncio.sleep(5)
                return await get_classplus_content(session, headers, batch_token, folder_id, level)
            
            data = await res.json()
            for item in data.get('data', []):
                name = item['name']
                if item['contentType'] == 1: # Folder
                    indent = "  " * level
                    results.append(f"\n{indent}📁 {name.upper()}\n{indent}{'━' * (len(name)+2)}")
                    nested_res, vc, pc, ic = await get_classplus_content(session, headers, batch_token, item['id'], level + 1)
                    results.extend(nested_res)
                    v_count += vc; p_count += pc; i_count += ic
                else:
                    raw_url = item.get('url') or item.get('thumbnailUrl', '')
                    # Video conversion logic (CDN to M3U8)
                    if "classplusapp.com" in raw_url and raw_url.endswith(('.jpg', '.png', '.jpeg')):
                        if "tencent" in raw_url:
                            raw_url = raw_url.rsplit('/', 1)[0] + "/master.m3u8"
                        else:
                            v_id = raw_url.split('/')[-3] if "drm" in raw_url else raw_url.split('/')[-1].split('.')[0]
                            raw_url = f"https://media-cdn.classplusapp.com/master.m3u8?id={v_id}"

                    indent = "  " * level
                    if item['contentType'] == 2: # Video
                        results.append(f"{indent}🎬 {name}: {raw_url}")
                        v_count += 1
                    elif item['contentType'] == 3: # PDF
                        results.append(f"{indent}📄 {name}: {raw_url}")
                        p_count += 1
                    else:
                        results.append(f"{indent}🖼 {name}: {raw_url}")
                        i_count += 1
            
        return results, v_count, p_count, i_count
    except Exception:
        return results, v_count, p_count, i_count

async def process_classplus(bot: Client, m: Message, user_id: int):
    # Current User Details
    user = await bot.get_users(user_id)
    mention = f'<a href="tg://user?id={user_id}">{user.first_name}</a>'
    time_new = datetime.now(india_timezone).strftime("%d-%m-%Y %I:%M %p")
    
    headers = {
        'api-version': '35',
        'device-id': 'c28d3cb16bbdac01',
        'user-agent': 'Mobile-Android',
        'x-access-token': 'YOUR_TOKEN_HERE' # config.TOKEN use karein
    }

    editable = await m.reply_text("✨ **Wait... Initializing Nova Extractor**")
    
    try:
        await editable.edit("**Enter ORG Code Of Your Classplus App**")
        org_msg = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
        org_code = org_msg.text.lower()
        await org_msg.delete()

        async with aiohttp.ClientSession() as session:
            # Hash fetch logic
            async with session.get(f"https://{org_code}.courses.store") as r:
                token_match = re.search(r'"hash":"(.*?)"', await r.text())
                if not token_match: return await editable.edit("❌ **Invalid Org Code**")
                store_hash = token_match.group(1)

            # Fetch batches
            list_url = "https://api.classplusapp.com/v2/course/search/published?limit=100&status=published"
            async with session.get(list_url, headers=headers) as lr:
                courses = (await lr.json()).get('data', {}).get('courses', [])
            
            if not courses: return await editable.edit("❌ **No Batches Found**")

            menu = [f"📚 **Available Batches for {org_code.upper()}:**\n"]
            for i, c in enumerate(courses, 1):
                menu.append(f"{i}. `{c['name']}`")
            
            await editable.edit("\n".join(menu) + "\n\n**Send Index Number (e.g. 1 or 1&2)**")
            
            idx_msg = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
            selections = idx_msg.text.split('&')
            await idx_msg.delete()

            for idx in selections:
                if not idx.strip().isdigit(): continue
                target = courses[int(idx)-1]
                b_name = target['name']

                await editable.edit(f"📥 **Extracting:** `{b_name}`")

                # Get Batch Details
                info_api = f"https://api.classplusapp.com/v2/course/preview/org/info?courseId={target['id']}"
                async with session.get(info_api, headers=headers) as ir:
                    res_data = await ir.json()
                    batch_token = res_data['data']['hash']
                    app_name = res_data['data'].get('name', org_code.upper())

                start_time = datetime.now()
                content, vc, pc, ic = await get_classplus_content(session, headers, batch_token)
                end_time = datetime.now()
                
                duration = end_time - start_time
                time_taken = f"{duration.seconds} seconds" if duration.seconds < 60 else f"{duration.seconds // 60}m {duration.seconds % 60}s"

                # TXT File Formatting
                file_name = f"{b_name.replace(' ', '_')}.txt"
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(f"BATCH: {b_name}\nEXTRACTED BY: {user.first_name}\n{'━'*30}\n\n")
                    f.write("\n".join(content))

                # --- NOVA STYLE EXTRACTION REPORT ---
                caption = (
                    f"࿇ ══━━{mention}━━══ ࿇\n\n"
                    f"🌀 **Aᴘᴘ Nᴀᴍᴇ** : {app_name}\n"
                    f"🔑 **Oʀɢ Cᴏᴅᴇ** : `{org_code.upper()}`\n"
                    f"============================\n\n"
                    f"🎯 **Bᴀᴛᴄʜ Nᴀᴍᴇ** : `{b_name}`\n"
                    f"<blockquote>🎬 : {vc} | 📁 : {pc} | 🖼 : {ic}</blockquote>\n\n"
                    f"🌐 **Jᴏɪɴ Us** : {join}\n"
                    f"⌛ **Tɪᴍᴇ Tᴀᴋᴇɴ** : {time_taken}</blockquote>\n\n"
                    f"❄️ **Dᴀᴛᴇ** : {time_new}"
                )

                await m.reply_document(file_name, caption=caption)
                await bot.send_document(CHANNEL_ID, file_name, caption=f"✅ **Extraction Successful**\n\n{caption}")
                os.remove(file_name)
                await asyncio.sleep(2)

        await editable.edit("✅ **All Batches Processed Successfully!**")

    except Exception as e:
        logging.error(e)
        await m.reply_text(f"⚠️ **Error:** `{str(e)}`")
