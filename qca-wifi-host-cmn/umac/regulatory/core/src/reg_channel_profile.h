/* SPDX-License-Identifier: ISC */
#ifndef _REG_CHANNEL_PROFILE_H_
#define _REG_CHANNEL_PROFILE_H_

#include <reg_services_public_struct.h>
#include "reg_db.h"

#ifdef CONFIG_WLAN_WIDE_CHANNELS
/**
 * reg_get_wide_channel_profile() - Make the compiled-in Onyx lab domain request
 *
 * FCC8_WORLD supplies the broad 5 GHz domain and channels 1-13. The target
 * interface separately programs MKKA for 2.4 GHz before adding the channel
 * 14 rule. FCC1_6G_09 requests the firmware's full-range 6 GHz LPI/SP domain.
 * Firmware/BDF, DFS, AFC, indoor, SAR and power checks remain active.
 *
 * Return: The base domain request, including 6 GHz when compiled in.
 */
static inline struct cc_regdmn_s reg_get_wide_channel_profile(void)
{
	struct cc_regdmn_s rd = {0};

	rd.flags = REGDMN_IS_SET;
	rd.cc.regdmn.reg_2g_5g_pair_id = FCC8_WORLD;
#ifdef CONFIG_BAND_6GHZ
	rd.cc.regdmn.sixg_superdmn_id = FCC1_6G_09;
#endif
	return rd;
}

/**
 * reg_cap_channel_profile_power() - Avoid increasing the existing TN ceilings
 * @info: Validated firmware channel-list event
 *
 * The broad domain has higher power allowances on some frequencies. Keep
 * the observed Onyx TN ceilings (20 dBm on 2.4 GHz, 23 dBm on 5 GHz), or
 * a lower firmware limit. Leave bandwidth, DFS and indoor flags untouched.
 */
static inline void
reg_cap_channel_profile_power(struct cur_regulatory_info *info)
{
	uint32_t i;

	if (info->reg_dmn_pair != FCC8_WORLD)
		return;

	for (i = 0; info->reg_rules_2g_ptr && i < info->num_2g_reg_rules; i++)
		if (info->reg_rules_2g_ptr[i].reg_power > 20)
			info->reg_rules_2g_ptr[i].reg_power = 20;

	for (i = 0; info->reg_rules_5g_ptr && i < info->num_5g_reg_rules; i++)
		if (info->reg_rules_5g_ptr[i].end_freq <= 5925 &&
		    info->reg_rules_5g_ptr[i].reg_power > 23)
			info->reg_rules_5g_ptr[i].reg_power = 23;
}
#else
static inline void
reg_cap_channel_profile_power(struct cur_regulatory_info *info)
{
}
#endif

#endif /* _REG_CHANNEL_PROFILE_H_ */
